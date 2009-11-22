import wsgiref.handlers, os
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from django.utils import simplejson
from google.appengine.ext import db
from google.appengine.api import users
import logging

class QueueModel(db.Model):
    qName = db.StringProperty()
    qValue = db.BlobProperty()
    qTStamp = db.DateTimeProperty(auto_now_add=True)
    qCount = db.IntegerProperty(default=0)

class ApiKeyStorage(db.Model):
    User = db.UserProperty()
    ApiKey = db.StringProperty()


class MainPage(webapp.RequestHandler):
    def get(self):
        _tpl = {}
        path = os.path.join(os.path.dirname(__file__), 'index.html')
        self.response.out.write(template.render(path, _tpl))


class Queue(webapp.RequestHandler):
    def get(self):
        _tpl = {'action': 'queue'}
        path = os.path.join(os.path.dirname(__file__), 'post.html')
        self.response.out.write(template.render(path, _tpl))

    def post(self):
        body = self.request.get("body")
        r = {}
        try:
            jsonbody = simplejson.loads(body)
        except Exception, e:
            r['error']="Malformed json: %s" % e
            self.error(500)
            self.response.out.write(simplejson.dumps(r))
            return
            
        if jsonbody == None:
            r['error']="No Data"
            self.error(500)
            self.response.out.write(simplejson.dumps(r))
            return
        
        cmd = jsonbody['cmd']
        
        if cmd == None or cmd == "":
            r['error']="CMD error"
            self.error(500)
            self.response.out.write(simplejson.dumps(r))
            return

#  api-key authorization hook
        a = self._authorize(jsonbody)
        if a == None:
            r['error']="No KEY error"
            self.error(401)
            self.response.out.write(simplejson.dumps(r))
            return
        
        if a == False:	
            r['error']="No Authorized User/Key"
            self.error(401)
            self.response.out.write(simplejson.dumps(r))
            return

        d = CommandDispatch()
        r=d.execute(cmd, jsonbody)
        
        if r == None: 
            self.error(404)
            self.response.out.write(simplejson.dumps({"error":"Null resultset"}))
            return

        if r.has_key("error"):
            self.error(404)
            logging.info(repr(r))
            self.response.out.write(simplejson.dumps(r))
            return

        self.response.out.write(simplejson.dumps(r))

    def _authorize(self, jsonbody):
        user = users.get_current_user()
        if jsonbody.has_key('apikey'):
            apikey = jsonbody['apikey']
            if apikey == None or apikey == "": 
                return None
        else:
            return None
        
        q = db.GqlQuery("SELECT * FROM ApiKeyStorage WHERE User = :1 AND ApiKey=:2", user, apikey)
        userprefs = q.get()
        if userprefs == None:
            return False
        else:
            return True

class CommandDispatch:
    # cmd: add, get, take, del
    def _add(self, jsonbody):
        r={}
        try:
            qitem = QueueModel(qName=jsonbody['queue'], qValue=str(jsonbody['value']))
            e=qitem.put()
            r['queue'] = jsonbody['queue']
            r['value'] = jsonbody['value']
            r['key'] = str(qitem.key())
            return r
        except Exception, e:
            return {"error":e}

    def _get(self, jsonbody): 
        r={}
        try:
            query = db.Query(QueueModel)
            query.filter('qName =', jsonbody['queue']).order('-qTStamp')
            res = query.fetch(1)
            if len(res) == 0 or res == None: return None

            v=res[0]	
            r['queue'] = jsonbody['queue']
            r['value'] = v.qValue
            r['key'] = str(v.key())
            r['count'] = v.qCount
            v.qCount=v.qCount+1
            v.save()
            return r
        except Exception, e:
            return {"error":e}

    def _take(self, jsonbody):
        r={}
        try:	
            query = db.Query(QueueModel)
            query.filter('qName =', jsonbody['queue']).order('-qTStamp')
            res = query.fetch(1)
            if res == None:
                r["msg"]="queue is empty"
                r['queue'] = jsonbody['queue']
                return r
            v=res[0]
            r = db.run_in_transaction(self._get_and_delete, v, jsonbody['queue'])
            return r
        except Exception, e:
            logging.error(e)
            r['error']="Transaction error for queue: %s [%s]" % (jsonbody["queue"], e)
            return r 
		
    def _del(self, jsonbody):
        r={}
        try:
            k = jsonbody['key']
            e=db.get(k)
            if e == None:
                r['error']="no such key: "+k
                return r
            logging.info(e.qName) 
            if e.qName == jsonbody['queue']:
                r['queue'] = jsonbody['queue']
                r['key'] = str(e.key())
                db.delete(e.key())
            else:
                r['error']="no such queue: "+jsonbody["queue"]

            return r
        except Exception, e:
            return {"error": str(e)}
			
    def _get_and_delete(self, row, queue):
        logging.error(repr(row))
        logging.error(row)
        r = {}
	r['queue'] = queue
	r['value'] = row.qValue
	r['key'] = str(row.key())
        db.delete(row.key())
        return r

    def execute(self, command, jsonbody):
        c = "_"+command
        if hasattr(self, c):
            m=getattr(self, c)
            return m(jsonbody)
        else:
            return None


class Admin(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        logging.info(repr(user))
        if user:
	    q = db.GqlQuery("SELECT * FROM ApiKeyStorage WHERE User = :1", user)
	    userprefs = q.get()
            if userprefs == None:
                _tpl = {'username': user, 'apikey': ""}
            else:
	        _tpl = {'username': user, 'apikey': userprefs.ApiKey}
	    path = os.path.join(os.path.dirname(__file__), 'admin.html')
	    self.response.out.write(template.render(path, _tpl))
        else:
	    out = ("<a href=\"%s\">Sign in or register</a>." % users.create_login_url("/admin"))
	    self.response.out.write("<html><body>%s</body></html>" % out)
		  
    def post(self):
        # post only updates the apikey... it's the place to customize user preferences
        from hashlib import sha1
        from time import time
	user = users.get_current_user()
        r={}
        if user:
	    q = db.GqlQuery("SELECT * FROM ApiKeyStorage WHERE User = :1", user)
	    userprefs = q.get()
	    if userprefs == None:
                logging.info("Creating user info")
                apikey = sha1("%s-%s" % (user.user_id(), time())).hexdigest()
                ks=ApiKeyStorage(User=user, ApiKey=apikey)
                ks.put()
            else:
                logging.info("Updating user info")
                logging.info(q.count())
                apikey = sha1("%s-%s" % (user.user_id(), time())).hexdigest()
                userprefs.ApiKey=apikey
                userprefs.save()
		
            _tpl = {'username': user, 'apikey': apikey}
	    path = os.path.join(os.path.dirname(__file__), 'admin.html')
	    self.response.out.write(template.render(path, _tpl))
	    return
	else:
	    r['error']="No User"
	    self.response.out.write(simplejson.dumps(r))


class Stats(webapp.RequestHandler):
    def get(self):
        path = self.request.path.split('/')[1:]
        r={}
        if len(path) > 1:
            query = db.Query(QueueModel)
            query.filter('qName =', path[1])
            c=query.count()
            r["queue"]=path[1]
            r["backlog"]=c
        else: # whole system backlog
            query = db.Query(QueueModel)
            c=query.count()
            r["queue"]="System Wide Queues"
            r["backlog"]=c
        self.response.out.write(simplejson.dumps(r))
        return

def main():
    app = webapp.WSGIApplication([('/', MainPage), ('/admin', Admin), ('/queue',Queue), ('/stats/.*',Stats), ('/stats', Stats)], debug=True)
    wsgiref.handlers.CGIHandler().run(app)

if __name__ == "__main__":
    main()
