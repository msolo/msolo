from wiseguy.examples.routes.basecontroller import BaseController

class Controller(BaseController):

    def index(self):
        self.status = '200 OK'
        self.response = 'This is the index'
        self.addheader(('Content-type','text/plain'))
        self.addheader(('Content-length', str(len(self.response))))
        self.start_response(self.status, self.response_headers)
        return [self.response]

    def hello(self):
        name = self.args.get('name', 'world')
        self.status = '200 OK'
        self.response = 'Hello %s' % name
        self.addheader(('Content-type','text/plain'))
        self.addheader(('Content-length', str(len(self.response))))
        self.start_response(self.status, self.response_headers)
        return [self.response]


            