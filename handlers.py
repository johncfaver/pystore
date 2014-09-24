#!/usr/bin/env python

#Request handlers for Pystore.

import os
import shutil
import time
import subprocess
import json
import sqlite3

from multiprocessing import Process

import tornado.web
from tornado.log import access_log

from helpers import *

class myApp(tornado.web.Application):
    def __init__(self, *args, **kwargs):
        """
        Override to define global database connection.
        If the database file is missing, create an empty one 
        using the createdb.sql script.
        Define sqlite3 function saltHash for password hashing.
        The definition of saltHash is in helpers.py
        """
        dbfilename = kwargs['database_file']
        if os.path.isfile(dbfilename):
            self.db = sqlite3.connect(dbfilename)
        else: 
            self.db = sqlite3.connect(dbfilename)
            with open('createdb.sql') as fsql:
                self.db.executescript(fsql.read())
        self.db.create_function("saltHash",2,saltHash)
        self.email_config = kwargs['email_config']
        tornado.web.Application.__init__(self, *args, **kwargs)

    def log_request(self, handler): 
        """
        Override to modify access log message to include timestamp.
        """ 
        log_method = access_log.info 
        timestamp = time.asctime(time.localtime(time.time()))
        try:
            user = handler.get_current_username()
        except Exception:
            user = '?'
        log_method("(%s) %s %d %s", user,timestamp,
                    handler.get_status(), handler._request_summary()) 

class myHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        """
        Override to define authentication status.
        Authentication requires a secure cookie named "user"
        """
        try:
            user = self.get_secure_cookie('user')
            user = json.loads(user)
            userid = user['userid']
            return True
        except Exception:
            return False
    def get_current_userid(self):
        return json.loads(self.get_secure_cookie('user'))['userid']
    def get_current_username(self):
        return json.loads(self.get_secure_cookie('user'))['username']
    def user_is_admin(self):
        return json.loads(self.get_secure_cookie('user'))['isadmin'] == "1"

class index(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Display front page.
        """
        username = self.get_current_username()
        isadmin = self.user_is_admin()
        self.render('index.html',username=username,isadmin=isadmin)

class upload(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Display form for file upload.
        """
        topHashtags = getTopHashtags(self.application.db,21)
        self.render('upload.html',topHashtags=topHashtags)

    @tornado.web.authenticated
    def post(self):
        """
        Handle file uploads. 
        First, update database.
        Put uploaded file in ./docs/{docid}/{filename}
        Notify users who have requested it (in a background process)
        """
        q = self.application.db.cursor()
        try:
            fileinfo = self.request.files['docfile'][0]
            upfilename = fileinfo['filename']
            assert(len(upfilename) > 0)
        except Exception:
            self.write("Error receiving file")
            return
        fileextension = os.path.splitext(upfilename)[1]
        description = self.get_argument("description","")
        hashtags = getHashtags(description)
        authorid = self.get_current_userid()
        authorname = self.get_current_username()
        q.execute('INSERT INTO documents (name,authorid,dateadded,description) VALUES (?,?,?,?)', \
                    [upfilename,authorid,time.time(),description])
        docid = str(q.lastrowid)
        q.executemany('INSERT INTO hashtags (hashtag,docid) VALUES (?,?)',[ (hashtag,docid) for hashtag in hashtags ])
        try:
            os.mkdir(os.path.join(os.path.dirname(__file__),'docs/'+docid))
            newfile = os.path.join(os.path.dirname(__file__),'docs/'+docid+'/'+upfilename)
            os.symlink(upfilename,os.path.join(os.path.dirname(newfile),'file'+fileextension))
            with open(newfile,'w') as f:
                f.write(fileinfo['body'])
        except Exception as e:
            self.write("Error writing file: "+str(e))
            return    
        self.application.db.commit()
        update_process = Process(target=self.notifyUsers,args=(docid,upfilename,authorname,description))
        update_process.start()
        self.redirect('/view')
    
    def notifyUsers(self,docid,filename,author,desc):
        """
        Notify users which have requested notifications that
        a file has been uploaded.
        """
        q = self.application.db.cursor()
        q.execute('SELECT username from users where emailupdates = 1 and username != ?',[author])
        for row in q.fetchall():
            to_name =    row[0]
            to_address = to_name
            imsg = update_msg.format(to_name,author,docid,filename,desc)
            sendemail(to_address,update_subject,imsg,self.application.email_config)

class delete(myHandler):
    """
    Handle file deletion. 
    Remove row from documents table in database.
    Delete file from filesystem.
    Only allow original author or admin to delete files.
    """
    @tornado.web.authenticated
    def get(self,docid=None):
        if docid is not None:
            q = self.application.db.cursor()
            try:
                if self.user_is_admin():
                    q.execute('DELETE FROM documents WHERE docid=?',[docid])
                else:
                    userid = self.get_current_userid()
                    q.execute('DELETE FROM documents WHERE docid=? AND authorid=?',[docid,userid])
                if q.rowcount == 1:
                    q.execute('DELETE FROM hashtags WHERE docid=?',[docid])
                    shutil.rmtree(os.path.join(os.path.dirname(__file__),'docs/'+docid))
                self.application.db.commit()
            except Exception:
                self.write('ERROR DELETING')
                return
        self.redirect('/view')

class edit(myHandler):
    """ 
    Allow authors or admin to edit a file description.
    """
    @tornado.web.authenticated
    def get(self,docid=None):
        if docid is not None:
            q = self.application.db.cursor()
            q.execute('SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                            FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                            WHERE docid=?',[str(docid)])
            row = q.fetchone()
            if row is not None:
                doc = {'docid':       row[0],
                       'filename':    row[1],
                       'extension':   os.path.splitext(row[1])[1],
                       'author':      row[2],
                       'dateadded':   parseTimestamp(row[3]),
                       'description': row[4]}
            self.render('edit.html',doc=doc) 
        else:
            self.redirect('/view')

    @tornado.web.authenticated
    def post(self,docid=None):
        if docid is not None:
            q = self.application.db.cursor()
            newDesc = self.get_argument("newdescription","")
            newHashtags = getHashtags(newDesc)
            try:
                if self.user_is_admin():
                    q.execute('DELETE FROM hashtags WHERE docid=?',[docid])
                    q.executemany('INSERT INTO hashtags (hashtag,docid) VALUES (?,?)',
                                    [(hashtag,docid) for hashtag in newHashtags])
                    q.execute('UPDATE documents SET description=? WHERE docid=?',[newDesc,docid])
                else:
                    userid = self.get_current_userid()
                    q.execute('UPDATE documents SET description=? WHERE docid=? AND authorid=?',[newDesc,docid,userid])
                    if q.rowcount == 1:
                        q.execute('DELETE FROM hashtags WHERE docid=?',[docid])
                        q.executemany('INSERT INTO hashtags (hashtag,docid) VALUES (?,?)',
                                    [(hashtag,docid) for hashtag in newHashtags])
                self.application.db.commit()
            except Exception:
                self.write('ERROR EDITING')
                return
            self.redirect('/view/'+docid)
        else:
            self.redirect('/view')

class view(myHandler):
    """
    View single document (given a docid), else view all documents.
    """
    items_per_page = 25
    @tornado.web.authenticated
    def get(self, docid=None):
        q = self.application.db.cursor()
        doclist = []
        page = int(self.get_argument("page","1"))
        mode = self.get_argument("mode","table")
        if mode not in ["table","gallery"]:
            self.write("NO")
            return

        if docid is not None:
            if docid.isdigit(): #View single documentid e.g. /view/3
                q.execute('SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                            FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                            WHERE docid=?',[str(docid)])
            else:  #View by hashtag 
                q.execute('SELECT h.docid,d.name,u.username,d.dateadded,d.description\
                            FROM hashtags h LEFT JOIN documents d ON d.docid=h.docid \
                            LEFT JOIN users u ON u.userid=d.authorid WHERE  \
                            h.hashtag LIKE ?',['#{0}'.format(docid.lower())])
        else:      #View all
            q.execute('SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                        FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                        ORDER BY d.dateadded DESC LIMIT ? OFFSET ?',[self.items_per_page,(page-1)*self.items_per_page])
        for row in q.fetchall():
            extension = os.path.splitext(row[1])[1]
            doclist.append( {'docid':       row[0],
                             'filename':    row[1],
                             'extension':   extension,
                             'author':      row[2],
                             'dateadded':   parseTimestamp(row[3]),
                             'description': row[4]})
        if mode == "table":
            template = "table.html"
        elif mode == "gallery":
            template = "gallery.html"

        self.render(template,doclist=doclist,
                    tophashtags=getTopHashtags(self.application.db),
                    randomhashtags=getRandomHashtags(self.application.db),
                    page=page,items_per_page=self.items_per_page)


class search(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Present form for searching.
        """
        self.render('search.html')

    @tornado.web.authenticated
    def post(self):
        """
        Display search results.
        Searching is done by looking for the query string in 
        filename, author names, or descriptions. Searches are
        case-insensitive.
        """
        query = self.get_argument("query",'').upper()
        searchtype = self.get_argument("searchtype","all")
        query = '%{0}%'.format(query)
        q = self.application.db.cursor()
        if searchtype == "users":
            q.execute("SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                        FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                        WHERE upper(u.username) like ? \
                        ORDER BY d.dateadded DESC",[query])
        elif searchtype == "filenames":
            q.execute("SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                        FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                        WHERE upper(d.name) like ? \
                        ORDER BY d.dateadded DESC",[query])
        elif searchtype == "descriptions":
            q.execute("SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                        FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                        WHERE upper(d.description) like ? \
                        ORDER BY d.dateadded DESC",[query])
        else:
            q.execute('SELECT d.docid,d.name,u.username,d.dateadded,d.description \
                        FROM documents d LEFT JOIN users u ON u.userid=d.authorid \
                        WHERE upper(d.name) like ? OR     \
                              upper(u.username) like ? OR \
                              upper(d.description) like ? \
                        ORDER BY d.dateadded DESC',[query]*3)
        results = []
        for row in q.fetchall():
            results.append( {'docid':       row[0],
                             'filename':    row[1],
                             'extension':   os.path.splitext(row[1])[1],
                             'author':      row[2],
                             'dateadded':   parseTimestamp(row[3]),
                             'description': row[4]})
        self.render('table.html',doclist=results,tophashtags=[],randomhashtags=[])

class hashtags(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Display hash tags in use.
        """
        allHashtags = getAllHashtags(self.application.db)
        self.render('hashtags.html',hashtags=allHashtags)

class admin(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Display Admin panel.
        """
        if self.user_is_admin():
            q = self.application.db.cursor()
            q.execute('SELECT userid,username,isadmin,emailupdates,email FROM users')
            users = []
            for row in q.fetchall():
                users.append( {"userid":        row[0],
                               "username":      row[1],
                               "isadmin":       row[2],
                               "emailupdates":  row[3],
                               "email":         row[4]}) 
            self.render('admin.html',users=users)
        else:
            self.redirect('/')

    @tornado.web.authenticated
    def post(self):
        """
        Handler admin actions.
        Actions include:
            1) generatePasswordKey -> generate key for password changes
        """
        if self.user_is_admin():
            userid = self.get_argument("userid",None)
            action = self.get_argument("action",None)
            if None in [userid,action]:
                self.write('Error doing stuff')
            if action == 'generatePasswordKey':
                q = self.application.db.cursor()
                q.execute('INSERT INTO passwordresets (resetkey,userid,\
                            daterequested) VALUES (?,?,?) ',
                            [genSalt(50),userid,time.time()])
                self.application.db.commit()
                self.redirect('/admin')
        else:
            self.redirect('/')

class invite(myHandler):
    @tornado.web.authenticated
    def post(self):
        """
        Send email invitation to create new user.
        """
        if self.user_is_admin:
            emails = find_email_addresses(self.get_argument("email_invitations"))
            for email in emails:
                invitekey = genSalt(50)
                q = self.application.db.cursor()
                q.execute('INSERT INTO invites (key,email) VALUES (?,?)', \
                         [invitekey,email])
                self.application.db.commit()
                message = invite_msg.format(invitekey)
                sendemail(email,invite_subject,message,self.application.email_config)
        self.redirect('/admin')

class register(myHandler):
    def get(self,invitationkey=''):
        """
        Form for new user registration.
        """
        q = self.application.db.cursor()
        q.execute('SELECT inviteid,email from invites where key=?',[invitationkey])
        row = q.fetchone()
        if row is not None:
            inviteid,email = row[0],row[1]
        else:
            inviteid,email = None,None
        self.render('register.html',email=email,inviteid=inviteid)

    def post(self,invitationkey=''):
        """
        Handle new user registration.
        """
        email = self.get_argument("email",None)
        username = self.get_argument("username",None)            
        password = self.get_argument("password",None)
        emailupdates = self.get_argument("emailupdates",None)
        if None in [email,username,password,emailupdates]:
            self.redirect(r'/')
        salt = genSalt()
        q = self.application.db.cursor()
        q.execute('INSERT INTO users (username,password,salt,emailupdates,email) \
                          VALUES (?,?,?,?,?) ',[username,saltHash(password,salt),
                          salt,emailupdates,email])
        q.execute("DELETE FROM invites WHERE key=?",[invitationkey])
        self.application.db.commit()
        self.redirect(r'/')

class passwordReset(myHandler):
    def get(self,key=None):
        """
        Present page for password reset.
        Requires password change key. 
        Password must be changed within 24 hours of request.
        """
        user = self.getKeyInfo(key)
        if user is not None:
            self.render('changepassword.html',user=user)
        else:
            self.write('Bad key!')

    def post(self,key=None):
        """
        Check for valid password change.
        """
        username = self.get_argument("username",None)            
        newpassword = self.get_argument("newpassword",None)
        if None in [username,newpassword,key] or not self.getKeyInfo(key):
            self.write('BAD REQUEST')
        salt = genSalt()
        q = self.application.db.cursor()
        q.execute('UPDATE users SET password=?,salt=? WHERE username=?', 
                     [saltHash(newpassword,salt),salt,username])
        q.execute("UPDATE passwordresets set waschanged=1,datechanged=? \
                    WHERE resetkey=?",[time.time(),key])
        self.application.db.commit()
        self.redirect(r'/')

    def getKeyInfo(self,key=None):
        """
        Verify that password change key is valid.
        Key must be unused, and less than 24 hours old. 
        """
        user = None
        if key is not None:
            q = self.application.db.cursor()
            q.execute('SELECT p.userid,u.username \
                        FROM passwordresets p LEFT JOIN users u ON u.userid=p.userid \
                        WHERE p.resetkey=? AND p.waschanged = 0 AND \
                        (? - p.daterequested) < 86400',[key,time.time()])
            row = q.fetchone()
            if row is not None:
                user = { 'resetkey':    key,
                         'userid':      row[0],
                         'username':    row[1]}
        return user

class userSettings(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Display form for updating user settings.
        """
        q = self.application.db.cursor()
        userid = self.get_current_userid()
        username = self.get_current_username()
        q.execute('SELECT emailupdates from users where userid=?',[userid])    
        oldemailupdates = q.fetchone()[0]
        userdata = {'username':username,'emailupdates':oldemailupdates}
        self.render('settings.html',userdata=userdata)

    @tornado.web.authenticated
    def post(self):
        """
        Handle updates for user settings.
        """
        new = self.get_argument("emailupdates")
        old = self.get_argument("oldemailupdates")
        userid = self.get_current_userid()
        if new != old:
            q = self.application.db.cursor()
            q.execute('UPDATE users SET emailupdates=? WHERE userid=?',[new,userid])
            self.application.db.commit()
        self.redirect('/')

class login(myHandler):
    def get(self):
        """
        Present form for login. 
        Display error messages in "status" argument.
        """
        status = self.get_argument("status",'')
        if status == 'fail':
            message = "Invalid login."
        else:
            message = None
        self.render('login.html',message=message)

    def post(self):
        """
        Verify login information. 
        Store userid, username in secure cookie.
        """
        username = self.get_argument("username","")
        password = self.get_argument("password","")
        q = self.application.db.cursor()
        q.execute('SELECT userid,isadmin FROM users WHERE username = ? AND password = saltHash(?,salt)',[username,password])
        row = q.fetchone()
        if row is not None:
            userid  = str(row[0])
            isadmin = str(row[1])
            user_info = { 'userid':     userid,
                          'username':   username,
                          'isadmin':    isadmin}
            user_info = json.dumps(user_info)
            self.set_secure_cookie("user",user_info,expires_days=3)
            self.redirect(r'/')
        else:
            self.redirect(r'/login?status=fail')

class logout(myHandler):
    @tornado.web.authenticated
    def get(self):
        """
        Clear cookie and logout.
        """
        self.clear_cookie("user")
        self.redirect('/')

class problem(myHandler):
    @tornado.web.authenticated
    def get(self,req='?'):
        """
        Display Error page.
        """
        self.render('error.html',req=req)
       
class docsGet(tornado.web.StaticFileHandler):
    """
    Override StaticFileHanlder to require authentication for document downloads.
    """
    @tornado.web.authenticated
    def get(self, path):
        super(docsGet,self).get(path)

    def get_current_user(self):
        try:
            user = self.get_secure_cookie("user")
            user = json.loads(user)
            userid = user['userid'] 
            return True
        except Exception:
            return False

    def get_current_username(self):
        try:
            user = self.get_secure_cookie("user")
            user = json.loads(user)
            username = user['username'] 
            return username
        except Exception:
            return None


