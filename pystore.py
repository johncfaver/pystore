#!/usr/bin/env python

# Webapp for uploading/downloading/viewing/searching arbitrary files/documents
# Access to any of these functions is available only to registered users found
# in the sqlite database file. 
#
# 2014 John Faver (johncfaver@gmail.com)

import os
import logging
import tornado.log
import tornado.ioloop

import handlers

################OPTIONS##############################
#Name of the application
app_name  = "Pystore"

#HTTPS requires certificate and key files. They should be
#placed in the /cert directory. Provide their filenames here.
use_ssl   = False
crt_file  = ""
key_file  = "" 

#Port for server.
app_port  = 8881

#Domain name or IP address of this service. 
domain = ""

#Settings for outgoing email. 
#Used for invitations, password resets, updates.
email_config = { 'from_address': '',
                 'host':         '',
                 'port':          0,
                 'user':         '',
                 'password':     ''
               }

#Location of sqlite database file. Default is Pystore.sqlite
database_file = os.path.join(os.path.dirname(__file__),app_name+'.sqlite')

#Names of log files
accesslogfile = app_name+'_access.log'
errorlogfile  = app_name+'_error.log'

#Email body for invitations
invite_msg = """
Hi there,

    You have been invited to join {0}.
This service is used to store and share documents with other users.
To create an account, use this personalized link:

{1}/register/{2}

""".format(app_name,domain,'{0}')
invite_subject = "Invitation to {0}".format(app_name)

#Email body for updates (on new uploads)
update_msg = """
Hi {0},

    {1} just uploaded a new document to {2}:

       Filename: {3}/docs/{4}/{5}

       Description: "{6}"

    (Update your account if you don't want these notifications.)
""".format('{0}','{1}',app_name,domain,'{2}','{3}','{4}')
#Email subject for updates (on new uploads)
update_subject = "New document available on {0}".format(app_name)

###############END OPTIONS##########################################

if __name__ == '__main__':
    
    this_dir = os.path.dirname(__file__)

    app_handlers = [
        (r'/',               handlers.index),
        (r'/upload',         handlers.upload),
        (r'/view/(.*)',      handlers.view),
        (r'/view',           handlers.view),
        (r'/hashtags',       handlers.hashtags),
        (r'/delete/(\d+)',   handlers.delete),
        (r'/edit/(\d+)',     handlers.edit),
        (r'/search',         handlers.search),
        (r'/admin',          handlers.admin),
        (r'/invite',         handlers.invite),
        (r'/register/(\w+)', handlers.register),
        (r'/password/(\w+)', handlers.passwordReset),
        (r'/settings',       handlers.userSettings),
        (r'/login',          handlers.login),
        (r'/logout',         handlers.logout),
        (r'/docs/(.*)',      handlers.docsGet,{'path':os.path.join(this_dir,'docs')}),
        (r'/(.*)',           handlers.problem)
    ]

    options = { 'debug':             False,
                'gzip':              True,
                'template_path':     os.path.join(this_dir,'templates'),
                'static_path':       os.path.join(this_dir,'static'),
                'login_url':         "/login",
                'cookie_secret':     "E3kXxr03OIbb4eER89UBitdqePzeAE",
                'xsrf_cookies':      True,
                'database_file':     database_file,
                'email_config':      email_config
              }

    app = handlers.myApp(app_handlers,**options)

    accesslog = logging.handlers.RotatingFileHandler(accesslogfile,maxBytes=5000000,backupCount=10)
    tornado.log.access_log.setLevel(logging.INFO)
    tornado.log.access_log.addHandler(accesslog)
   
    errorlog = logging.handlers.RotatingFileHandler(errorlogfile,maxBytes=5000000,backupCount=10)
    tornado.log.app_log.setLevel(logging.INFO)
    tornado.log.gen_log.setLevel(logging.INFO)
    tornado.log.app_log.addHandler(errorlog)
    tornado.log.gen_log.addHandler(errorlog)

    if use_ssl:
        ssl_options = { "certfile": os.path.join(this_dir,crt_file),
                        "keyfile" : os.path.join(this_dir,key_file)
                      }
        app.listen(app_port,ssl_options=ssl_options)
    else:
        app.listen(app_port)
    tornado.ioloop.IOLoop.instance().start()
   
