#!/usr/bin/env python

# Helper functions for Pystore

import re
import smtplib
import time

from random import choice
from string import ascii_letters,digits
from hashlib import sha256
from email.mime.text import MIMEText


__all__ = ["saltHash","genSalt","parseTimestamp","find_email_addresses","sendemail",
            "getHashtags","getTopHashtags","getAllHashtags","getRandomHashtags"]

#Regex for finding email addresses
email_search = re.compile(r'[^@\s,=\?<>:\\\/]+@[^@\s,=\?<>:\\\/]+\.[^@\s,\?=<>:\\\/]+')
#Regex for finding hashtags
hashtag_search = re.compile(r'#[^\s]+')
#Set of characters to use when generating pseudorandom strings.
charset = ascii_letters + digits

def saltHash(text,salt=''):
    """
    Take input text, append salt, return digest.
    """
    text += salt
    return sha256(text).hexdigest()

def genSalt(salt_length=20):
    """
    Generate random string of numbers/letters.
    Used for password salts, invitation keys, password change keys.
    """
    return ''.join([ choice(charset) for i in xrange(salt_length)])

def parseTimestamp(timestamp):
    """
    Convert timestamp to human-readable format.
    """
    return time.strftime('%b %d, %Y',time.localtime(timestamp))

def find_email_addresses(instring):
    """
    Parse string, return list of email addresses.
    """
    list_of_addresses = email_search.findall(instring)
    return list_of_addresses

def sendemail(to_address,subject,text,email_config,tls=True,auth=True):
    """
    Send an email to to_addr containing text.
    """
    from_address = email_config['from_address']
    host         = email_config['host']
    port         = email_config['port']
    user         = email_config['user']
    password     = email_config['password']

    msg = MIMEText(text)
    msg['Subject'] = subject
    msg['From'] = from_address
    msg['To'] = to_address

    s = smtplib.SMTP(host,port)
    s.ehlo()
    if tls:
        s.starttls()
        s.ehlo()
    if auth:
        s.login(user,password)
    s.sendmail(from_address,to_address,msg.as_string())
    s.quit()

def getHashtags(text):
    """
    Return list of hashtags in a string.
    Convert hashtags to lowercase.
    """
    tags = hashtag_search.findall(text)
    tags = [ tag.lower() for tag in tags ]
    return tags

def getTopHashtags(dbconn,maxhashtags=8):
    """
    Return list of most frequent hashtags in database.
    """
    q = dbconn.cursor()
    q.execute('SELECT hashtag,COUNT(docid) AS num FROM hashtags \
                GROUP BY hashtag ORDER BY num DESC LIMIT ?',[maxhashtags])
    return [ row for row in q.fetchall() ]

def getAllHashtags(dbconn):
    """
    Return list of all hashtags in database ordered by frequency.
    """
    q = dbconn.cursor()
    q.execute('SELECT hashtag,COUNT(docid) AS num FROM hashtags \
                GROUP BY hashtag ORDER BY num DESC')
    return [ row for row in q.fetchall() ]

def getRandomHashtags(dbconn,probability=0.5,maxhashtags=8):
    """
    Return a list of random hashtags in database.
    """
    q = dbconn.cursor() 
    q.execute('SELECT hashtag FROM hashtags ORDER BY RANDOM() limit ?',[maxhashtags])
    # May need to use the below statement instead for larger tables
    #probability = int(round(1./probability))
    #q.execute('SELECT hashtag FROM hashtags WHERE RANDOM() % ? limit ?',[probability,maxhashtags])
    return [ row[0] for row in q.fetchall() ]

