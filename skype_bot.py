import datetime, time
from threading import Thread
from subprocess import Popen
from skpy import SkypeEventLoop, SkypeNewMessageEvent
import urllib.request
import jenkins
from jenkins import NotFoundException
import pandas as pd

server = jenkins.Jenkins('JENKINS_URL', username='JENKINS_USER_NAME', password='JENKINS_USER_PWD')
user = server.get_whoami()
version = server.get_version()

"""
Please follow format as below with or without spaces.
    1 : SHUTDOWN : {server name}
    2 : RESTART : {server name}
    3 : BUILD : {server name}
    4 : DEPLOY : {server name} : FOR -> B{number}
    5 : DOWNLOAD : Release
"""

class SkypeBot:
    someone_called_me = False
    assigned_task_to_me = False

    restart_script_path = '/usr/local/weblogic-domain/CMP/skype_bot/server_restart.sh %s %s'
    confluence_weblogic_url = str('ENV_DETAILS_URL')

    release_package_uri = str('RELEASE_PACKAGE_URL')

    server_details_df = pd.read_excel('C:\\Users\\Desktop\\Skype_Bot_Env_details.xlsx', sheet_name='Server and Job Details')
    list_of_server_names = server_details_df['Server Name']
    list_of_supported_operations = server_details_df['Operation']

    build_in_progress_list = []
    deployment_in_progress_list = []
    shutdown_in_progress_list = []
    restart_in_progress_list = []

    @classmethod
    def is_supported_operation(cls, operation_name, sub_op_name):

        row_values = cls.server_details_df[cls.list_of_supported_operations == operation_name].get(key='Operation')

        if cls.is_supported_sub_operation(operation_name, sub_op_name):
            return True

        if str(row_values.iloc[0]) == operation_name:
            return True

    @classmethod
    def is_supported_sub_operation(cls, operation_name, sub_op_name):
        row_values = cls.server_details_df[cls.list_of_supported_operations == operation_name].get(
            key='Sub Operation')

        if sub_op_name in row_values.to_dict().values():
            return True;

    @classmethod
    def is_valid_server_name(cls, server_name):
        if cls.server_details_df[cls.list_of_server_names == server_name].size > 0:
            return True

    @classmethod
    def get_jenkins_build_job_by_server_name(cls, server_name):
        value = cls.server_details_df[cls.list_of_server_names == server_name].get(key='Jenkins Deploy Job Name')
        if value is not None:
            return str(value.iloc[0])
        else:
            return value

    @classmethod
    def get_jenkins_deploy_job_by_server_name(cls, server_name):
        value = cls.server_details_df[cls.list_of_server_names == server_name].get(key='Jenkins Build Job Name')
        if value is not None:
            return str(value.iloc[0])
        else:
            return value

    @classmethod
    def get_server_url_by_server_name(cls, server_name):
        value = cls.server_details_df[cls.list_of_server_names == server_name].get(key='Server URL')
        if value is not None:
            return str(value.iloc[0])
        else:
            return value

    @classmethod
    def add_shutdown_request(cls, job_name):
        cls.shutdown_in_progress_list.append(job_name)

    @classmethod
    def add_restart_request(cls, job_name):
        cls.restart_in_progress_list.append(job_name)

    @classmethod
    def add_build_request(cls, job_name):
        cls.build_in_progress_list.append(job_name)

    @classmethod
    def add_deploy_request(cls, job_name):
        cls.deployment_in_progress_list.append(job_name)

    @classmethod
    def get_release_package_url(cls, release_version):
        return str(cls.release_package_uri.format(release_version, release_version))


def should_service(raw_message):
    if raw_message.lower().__contains__("hey bot"):
        return True


def say_welcome(raw_message, event, user_name):
    if raw_message.lower().__contains__("thanks bot"):
        event.msg.chat.sendMsg("You're Welcome! {0}".format(user_name))


def is_valid_request(message, event):
    if is_valid_operation(message, event):
        SkypeBot.assigned_task_to_me = True
        return True
    else:
        set_default_values_skype_bot()


def send_invalid_request_response(event, message):
    event.msg.chat.sendMsg(message)
    set_default_values_skype_bot()


def set_default_values_skype_bot():
    SkypeBot.someone_called_me = False
    SkypeBot.assigned_task_to_me = False


def is_valid_operation(message, event):
    try:
        operation_name = message.lower().split(":")[0]
        parameter = message.lower().split(":")[1]

        if operation_name is None or parameter is None:
            send_invalid_request_response(event, "Sorry..Please enter valid request format!")
            return False
        else:
            if SkypeBot.is_supported_operation(operation_name.lower(), parameter.lower()):
                if SkypeBot.is_valid_server_name(parameter.lower()):
                    return True
                else:
                    event.msg.chat.sendMsg("Sorry..Please enter valid server name.")
                    event.msg.chat.sendMsg(rich=True, content="You can refer to our confluence page -> {0}".format(SkypeBot.confluence_weblogic_url))
                    return False
            else:
                send_invalid_request_response(event, "oops.. I am not programmed to do that!")
                return False

    except IndexError:
        send_invalid_request_response(event, "Sorry..Please enter valid request format!")
        return False


def serve_request(raw_message, server_name, event):
    if raw_message.lower().__contains__("shutdown"):
        shutdown_serer('SHUTDOWN', server_name.strip(), event)

    elif raw_message.lower().__contains__("restart"):
        restart_serer('RESTART', server_name.strip(), event)

    elif raw_message.lower().__contains__("build"):
        build_or_deploy_server('BUILD', server_name.strip(), None, event)

    elif raw_message.lower().__contains__("deploy"):
        build_no_to_be_deployed = raw_message.lower().split("-&gt;")[1]
        build_or_deploy_server('DEPLOY', server_name.strip(), build_no_to_be_deployed, event)

    elif raw_message.lower().__contains__("download"):
        event.msg.chat.sendMsg("Sure!")
        event.msg.chat.sendMsg("Here you go..")
        event.msg.chat.sendMsg(rich=True, content=SkypeBot.get_release_package_url(get_latest_release_number()), )


def get_latest_release_number():
    last_build_number = server.get_job_info('RMT-Release')['lastBuild']['number']
    build_info = server.get_build_info('RMT-Release', last_build_number)
    return build_info['actions'][0]['parameters'][1]['value']


def shutdown_serer(task_name, server_name, event):
    if SkypeBot.shutdown_in_progress_list.__contains__(server_name):
        event.msg.chat.sendMsg("Shutdown already requested for : {0}".format(server_name))
    else:
        SkypeBot.add_shutdown_request(server_name)
        event.msg.chat.sendMsg("Sure!")
        ts = time.time()
        timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        print("Shutting Down Server : {0} @ {1}".format(server_name, timestamp))
        Popen(SkypeBot.restart_script_path % (str(task_name), str(server_name)), shell=True)

        check_shutdown_status(server_name, event)


def check_shutdown_status(server_name, event):
    server_url = SkypeBot.get_server_url_by_server_name(server_name)
    try:
        if urllib.request.urlopen(server_url).getcode() != 200:
            event.msg.chat.sendMsg("Shutdown successfully : {0} -> {1}".format(server_name, server_url))

    except Exception:
        print("Failed to check Shutdown status for server {0}".format(server_name))

    SkypeBot.shutdown_in_progress_list.clear()
    set_default_values_skype_bot()


def restart_serer(task_name, server_name, event):
    if SkypeBot.restart_in_progress_list.__contains__(server_name):
        event.msg.chat.sendMsg("Restart already requested for : {0}".format(server_name))

    else:
        SkypeBot.add_restart_request(server_name)
        event.msg.chat.sendMsg("Sure!")
        ts = time.time()
        timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
        print("Restarting Server : {0} @ {1}".format(server_name, timestamp))
        Popen(SkypeBot.restart_script_path % (str(task_name), str(server_name)), shell=True)

        new_thread = Thread(target=check_restart_status, args=(server_name, event,), group=None)
        new_thread.start()
        print("Continue Listening Again..")


def check_restart_status(server_name, event):
    server_url = SkypeBot.get_server_url(server_name)
    still_starting = True
    while still_starting:
        try:
            time.sleep(30)
            if urllib.request.urlopen(server_url).getcode() == 200:
                still_starting = False
                server_url = str('<a href="' + server_url + '">' + server_url + '"</a>')
                event.msg.chat.sendMsg(rich=True,
                                       content="Restarted successfully : {0} -> {1}".format(server_name, server_url))
        except Exception:
            print("Failed to check Restart status for server {0}".format(server_name))

    SkypeBot.restart_in_progress_list.clear()
    set_default_values_skype_bot()

def build_or_deploy_server(task_name, server_name, build_no, event):
    ts = time.time()
    timestamp = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

    if task_name == 'BUILD':

        jenkins_job_name = SkypeBot.get_jenkins_build_job_by_server_name(server_name)

        if SkypeBot.build_in_progress_list.__contains__(jenkins_job_name):
            event.msg.chat.sendMsg("Build already requested for : {0}".format(jenkins_job_name))

        else:
            SkypeBot.add_build_request(jenkins_job_name)
            event.msg.chat.sendMsg("Sure!")
            print("Building Server : {0} @ {1}".format(server_name, timestamp))
            try:

                last_queue_number = server.get_job_info(jenkins_job_name)['lastBuild']['number']

                print("Build Number Before Trigger :" + str(last_queue_number))

                print(server.build_job(jenkins_job_name))
                th = Thread(target=check_build_status,
                            args=(jenkins_job_name, last_queue_number, event,), group=None)
                th.start()
                print("Continue Listening Again..")

            except NotFoundException:
                set_default_values_skype_bot()
                SkypeBot.build_in_progress_list.clear()
                print("NotFoundException")

    elif task_name == 'DEPLOY':

        jenkins_job_name = SkypeBot.get_jenkins_deploy_job_by_server_name(server_name)

        if SkypeBot.deployment_in_progress_list.__contains__(jenkins_job_name):
            event.msg.chat.sendMsg("Deployment already requested for : {0}".format(jenkins_job_name))

        else:
            SkypeBot.add_deploy_request(jenkins_job_name)
            event.msg.chat.sendMsg("Sure!")
            jira_build_no = build_no.upper()
            print("Deploying Server : {0} for Build No : {1} @ {2}".format(server_name, jira_build_no, timestamp))
            try:
                last_queue_number = server.get_job_info(jenkins_job_name)['lastBuild']['number']
                print(server.build_job(jenkins_job_name, token=jenkins_job_name,
                                       parameters={'JIRA_REL_VERSION': jira_build_no}))

                new_thread = Thread(target=check_deployment_status,
                                    args=(jenkins_job_name, last_queue_number, event,), group=None)
                new_thread.start()
                print("Continue Listening Again..")

            except NotFoundException:
                set_default_values_skype_bot()
                SkypeBot.deployment_in_progress_list.clear()
                print("NotFoundException")


def check_build_status(jenkins_job_name, last_queue_number, event):
    print("Checking build status for : {0}".format(jenkins_job_name))

    still_in_progress = True
    while still_in_progress:
        time.sleep(30)
        print('Checking Build Status for : {0} with queue number : {1}'.format(jenkins_job_name,
                                                                               str(last_queue_number + 1)))
        current_status = server.get_build_info(jenkins_job_name, last_queue_number + 1)['result']
        still_in_progress = bool(server.get_build_info(jenkins_job_name, last_queue_number + 1)['building'])

    if still_in_progress is False:
        if current_status.lower().__contains__("success") or current_status.lower().__contains__("unstable"):
            event.msg.chat.sendMsg("BUILD SUCCESSFUL for : {0}".format(jenkins_job_name))
            print("Build Successfully for Job : {0}".format(jenkins_job_name))

        elif current_status.lower().__contains__("fail"):
            event.msg.chat.sendMsg("BUILD FAILED for : " + jenkins_job_name)
            print("Build Failed for Job : {0}".format(jenkins_job_name))

    else:
        event.msg.chat.sendMsg("BUILD FAILED ABRUPTLY for : {0}".format(jenkins_job_name))
        print("Build Failed Abruptly for : {0}".format(jenkins_job_name))

    SkypeBot.build_in_progress_list.clear()
    set_default_values_skype_bot()


def check_deployment_status(jenkins_job_name, last_queue_number, event):
    print("Checking Deployment status for : {0}".format(jenkins_job_name))

    still_in_progress = True
    while still_in_progress:
        time.sleep(30)
        print('Checking Deployment Status for : {0} with queue number : {1}'.format(jenkins_job_name, str(last_queue_number + 1)))
        current_status = server.get_build_info(jenkins_job_name, last_queue_number + 1)['result']
        still_in_progress = bool(server.get_build_info(jenkins_job_name, last_queue_number + 1)['building'])

    if still_in_progress is False:
        if current_status.lower().__contains__("success") or current_status.lower().__contains__("unstable"):
            event.msg.chat.sendMsg("Deployment Successful for : {0}".format(jenkins_job_name))
            print("Deployment Successfully for Job : {0}".format(jenkins_job_name))

        elif current_status.lower().__contains__("fail"):
            event.msg.chat.sendMsg("Deployment Failed for : {0}".format(jenkins_job_name))
            print("Build Failed for Job : {0}".format(jenkins_job_name))

    else:
        event.msg.chat.sendMsg("Deployment Failed Abruptly for : {0}".format(jenkins_job_name))
        print("Deployment Failed Abruptly for : " + jenkins_job_name)

    SkypeBot.deployment_in_progress_list.clear()
    set_default_values_skype_bot()


class SkypeListener(SkypeEventLoop):
    def onEvent(self, event):

        if isinstance(event, SkypeNewMessageEvent):
            if event.type == 'NewMessage' and not event.msg.userId == self.userId:

                message = event.msg.content.lower();

                user_name = event.msg.user.name.first

                if user_name is None:
                    user_name = event.msg.user.raw['display_name']

                if user_name is None:
                    user_name = 'Friend'

                say_welcome(message, event, user_name)

                if SkypeBot.someone_called_me and not event.msg.userId == self.userId and not should_service(message):
                    if is_valid_request(message, event):
                        server_name = message.lower().split(":")[1]
                        serve_request(message, server_name, event)
                        set_default_values_skype_bot()

                if should_service(message):
                    SkypeBot.someone_called_me = True;

                    event.msg.chat.sendMsg("Hi {0}. I'm Skype Bot".format(user_name))
                    event.msg.chat.sendMsg("What would you like to do today?")
                    event.msg.chat.sendMsg('1 : SHUTDOWN : {server name}\n'
                                           '2 : RESTART : {server name}\n'
                                           '3 : BUILD : {server name}\n'
                                           '4 : DEPLOY : {server name} : FOR -> B{number}\n'
                                           '5 : DOWNLOAD : Release Package')


sk = SkypeListener(user="SKYPE_USER_NAME", pwd="SKYPE_USER_PWD")
sk.loop()
