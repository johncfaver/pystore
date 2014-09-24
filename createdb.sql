CREATE TABLE users     (userid INTEGER PRIMARY KEY AUTOINCREMENT, 
                        username TEXT NOT NULL, 
                        password TEXT NOT NULL,
                        salt TEXT NOT NULL,
                        isadmin INTEGER CHECK(isadmin in (0,1)) DEFAULT 0,
                        emailupdates INTEGER CHECK(emailupdates in (0,1)) DEFAULT 0,
                        email TEXT);

CREATE TABLE documents (docid INTEGER PRIMARY KEY AUTOINCREMENT, 
                        name TEXT NOT NULL, 
                        authorid INTEGER NOT NULL,
                        dateadded REAL,
                        description TEXT,
                        FOREIGN KEY(authorid) REFERENCES users(userid));

CREATE TABLE hashtags (hashtag TEXT NOT NULL,
                       docid INTEGER NOT NULL,
                       FOREIGN KEY(docid) REFERENCES documents(docid));

CREATE TABLE invites (inviteid INTEGER PRIMARY KEY AUTOINCREMENT,
                      key TEXT NOT NULL,
                      email TEXT NOT NULL);

CREATE TABLE passwordresets (resetkey TEXT NOT NULL,
                             userid INTEGER NOT NULL,
                             daterequested REAL NOT NULL,
                             datechanged REAL,
                             waschanged INTEGER CHECK(waschanged in (0,1)) DEFAULT 0,
                             FOREIGN KEY(userid) REFERENCES users(userid));            
/*Admin password is admin*/
INSERT INTO users (username,password,salt,isadmin) VALUES ('admin','8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918','',1);
