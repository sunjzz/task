"""Author ZhengZhong,Jiang"""


import os
import sys
import socketserver
import subprocess
import json
import re
import hashlib
from conf import settings
from core.initialize import initialize
from core.logged import log

class Comm(socketserver.BaseRequestHandler):
    user = ''
    user_state = 0
    current_path = user
    whoami = subprocess.Popen('whoami', shell=True, stdout=subprocess.PIPE).stdout.read().decode()

    @staticmethod
    def calehash(args):
        print(args)
        args = args.strip()
        m = hashlib.md5()
        with open(args, 'rb')as fp:
            while True:
                blk = fp.read(4096)
                if not blk:break
                m.update(blk)
        return m.hexdigest()

    def comm_cd(self, *args, **kwargs):
        file_path = args[0].get('file_path')
        if file_path == '..':
            if Comm.current_path == Comm.user:
                subprocess.Popen('cd %s/%s' % (settings.DATA_DIR, Comm.user),
                                 shell=True)
                self.request.send(bytes('200', encoding='utf8'))
                Comm.current_path = Comm.user
            else:
                file_path = "%s" % Comm.current_path
                path_list = file_path.split('/')
                path_list.pop()
                file_path = ''.join(path_list)
                cmd = subprocess.Popen('cd %s' % file_path,
                                       shell=True, stderr=subprocess.PIPE)
                res = cmd.stderr.read()
                send_data = bytes('200', encoding="utf8")
                self.request.send(send_data)
                Comm.current_path = file_path
        else:
            cmd = subprocess.Popen('cd %s%s/%s' % (settings.DATA_DIR, Comm.current_path, file_path),
                                   shell=True, stderr=subprocess.PIPE)
            res = cmd.stderr.read()
            if len(res):
                send_data = bytes('404', encoding="utf8")
                self.request.send(send_data)
                send_data = bytes("目录不存在！", encoding='utf8')
                self.request.send(send_data)
            else:
                send_data = bytes('200', encoding="utf8")
                self.request.send(send_data)
                Comm.current_path = '%s/%s' % (Comm.current_path, file_path)
                Comm.current_path = Comm.current_path
        log(Comm.user, 'cd %s' % Comm.current_path)

    def comm_mkdir(self, *args, **kwargs):
        # user_name = args[0].get('username')
        file_path = args[0].get('file_path')
        subprocess.Popen('mkdir -p %s%s/%s' % (settings.DATA_DIR, Comm.current_path, file_path), shell=True)
        log(Comm.user, 'mkdir %s/%s' % (Comm.current_path, file_path))

    def comm_ls(self, *args, **kwargs):
        file_path = args[0].get('file_path')
        if file_path == '.':
            file_path = ''
        cmd = subprocess.Popen('ls -l %s%s/%s' % (settings.DATA_DIR, Comm.current_path, file_path),
                               shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res = cmd.stdout.read()
        re_code = bytes('200', encoding='utf8')
        self.request.send(re_code)
        if len(res):
            res = re.sub(Comm.whoami.strip(), Comm.user, res.decode())
            res = bytes(res, encoding='utf8')
            self.request.send(res)
        else:
            res = cmd.stderr.read()
            self.request.send(res)
        log(Comm.user, 'ls %s/%s' % (Comm.current_path, file_path))

    def comm_put(self, *args, **kwargs):
        data = json.load(open('%s/user.db' % settings.DB_DIR, 'r'))
        # 获取用户的磁盘配额
        quota = data.get(Comm.user)[1]
        file_name = args[0].get('file_name')
        # file_path = args[0].get('file_name')
        # file_name = file_path.split('/').pop()
        file_size = args[0].get('file_size')
        file_hash = args[0].get('file_hash')
        # 计算当前磁盘配额空间
        cmd = subprocess.Popen('du -sb %s%s' % (settings.DATA_DIR, Comm.user),
                               shell=True, stdout=subprocess.PIPE)
        use_size = cmd.stdout.read().split()[0].strip()
        # 磁盘配额计算并判断
        print(file_size + int(use_size))
        print(quota*1024*1024)
        if file_size + int(use_size) >= quota*1024*1024:
            self.request.send(bytes("磁盘空间不够！", encoding='utf8'))
        else:
            self.request.send(bytes("200", encoding='utf-8'))
            f = open('%s/%s/%s' % (settings.DATA_DIR, Comm.current_path, file_name), 'wb')
            recv_size = 0
            while recv_size < file_size:
                data = self.request.recv(4096)
                f.write(data)
                recv_size += len(data)
            f.close()
            # 对上传完成的文件进行hash计算
            file_comp = Comm.calehash('%s%s/%s' % (settings.DATA_DIR, Comm.current_path, file_name))
            if file_comp == file_hash:
                self.request.send(bytes('文件校验一致！', encoding='utf8'))
            else:
                self.request.send(bytes('文件校验不一致！请重传！', encoding='utf8'))
            print("file recv success")
        log(Comm.user, 'put %s/%s' % (Comm.current_path, file_name))

    def comm_get(self, *args, **kwargs):
        user_name = args[0].get('username')
        file_name = args[0].get('file_name')
        file_path = '%s/%s' % (Comm.current_path, file_name)
        if os.path.exists(file_path):
            self.request.send(bytes('200', encoding='utf8'))
            file_info = json.loads(self.request.recv(1024).decode())
            if file_info['file_status'] == '401':
                file_size = file_info['file_size']
                client_confirmation_msg = self.request.recv(1024)
                confirm_data = json.loads(client_confirmation_msg.decode())
                f = open('%s%s/%s' % (settings.DATA_DIR, user_name, file_name), 'rb')
                f.seek(file_size)
                if confirm_data['status'] == 200:
                    for line in f:
                        self.request.send(line)
                    print("file send done")
                f.close()
                file_hash = Comm.calehash('%s%s/%s' % (settings.DATA_DIR, user_name, file_name))
                self.request.send(bytes("%s" % file_hash, encoding='utf8'))

            else:
                file_size = os.stat('%s%s/%s' % (settings.DATA_DIR, user_name, file_name)).st_size
                file_info = {'file_size': file_size}
                self.request.send(bytes(json.dumps(file_info), encoding='utf8'))
                client_confirmation_msg = self.request.recv(1024)
                confirm_data = json.loads(client_confirmation_msg.decode())
                f = open('%s%s/%s' % (settings.DATA_DIR, user_name, file_name), 'rb')
                if confirm_data['status'] == 200:
                    for line in f:
                        self.request.send(line)
                    print("file send done")
                f.close()
                file_hash = Comm.calehash('%s%s/%s' % (settings.DATA_DIR, user_name, file_name))
                self.request.send(bytes("%s" % file_hash, encoding='utf8'))
        else:
            self.request.send(bytes('404', encoding='utf8'))
        log(Comm.user, 'get %s/%s' % (Comm.current_path, file_name))


class Ftp(Comm):

    def reg(self):
        database = json.load(open("%s/user.db" % settings.DB_DIR, 'r'))
        recv_data = self.request.recv(1024)
        recv_dict = json.loads(recv_data.decode(), encoding='utf8')
        user_list = list(database.keys())
        if recv_dict['username'] in user_list:
            self.request.send(bytes('该用户已存在！', encoding='utf8'))
            log(Comm.user, '注册失败！')
        else:
            subprocess.Popen('mkdir %s/%s' % (settings.DATA_DIR, recv_dict['username']), shell=True)
            database[recv_dict['username']] = [recv_dict['password'], 500]
            json.dump(database, open("%s/user.db" % settings.DB_DIR, 'w'))
            self.request.send(bytes('注册成功！', encoding='utf8'))
            log(Comm.user, '注册成功！')

    def auth(self):
        while True:
            database = json.load(open("%s/user.db" % settings.DB_DIR, 'r'))
            data = self.request.recv(1024)
            recv_dict = json.loads(data.decode(), encoding='utf8')
            user_list = list(database.keys())
            Comm.user = recv_dict['username']
            if recv_dict['username'] in user_list:
                if recv_dict['password'] == database[recv_dict['username']][0]:
                    self.request.sendall(bytes("登录成功，欢迎！", encoding='utf8'))
                    log(Comm.user, '登录成功！')
                    Comm.user_state = 1
                    Comm.current_path = '%s' % Comm.user
                    state_code = json.dumps({"user_state": 1})
                    print(state_code)
                    self.request.sendall(bytes(state_code, encoding='utf8'))
                    break
                else:
                    self.request.sendall(bytes("密码错误！", encoding='utf8'))
                    log(Comm.user, '登录失败，密码错误！')
                    state_code = json.dumps({"user_state": 0})
                    self.request.sendall(bytes(state_code, encoding='utf8'))
                    break
            else:
                self.request.sendall(bytes("用户不存在！", encoding='utf8'))
                log(Comm.user, '登录失败，用户名不存在！')
                state_code = json.dumps({"user_state": 0})
                self.request.sendall(bytes(state_code, encoding='utf8'))
                break

    def handle(self):
        while True:
            choose = self.request.recv(1024)
            choose = choose.decode()
            if choose == 'reg':
                self.reg()
            else:
                self.auth()
                if Comm.user_state == 1:
                    while True:
                        data = self.request.recv(1024)
                        print(data.decode())
                        if len(data) == 0:
                            continue
                        else:
                            print('[%s] says: %s' % (self.client_address, data.decode()))
                            task_data = json.loads(data.decode())
                            task_data['username'] = self.user
                            task_action = task_data.get("action")
                            if hasattr(self, "comm_%s" % task_action):
                                func = getattr(self, "comm_%s" % task_action)
                                func(task_data)
                            else:
                                print("task action is not supported", task_action)


def start():
    initialize()
    server = socketserver.ThreadingTCPServer(('0.0.0.0', 8000), Ftp)
    server.serve_forever()
