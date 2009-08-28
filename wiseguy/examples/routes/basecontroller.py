class BaseController():

    def __init__(self, environ, start_response):
        self.environ = environ
        self.start_response = start_response
        self.args = self.extract_args()
        self.status = ''
        self.response = ''
        self.response_headers = []

    def send404(self):
        self.status = '404 PAGE NOT FOUND'
        self.response = "404 This page was not found"
        self.addheader(('Content-type','text/plain'))
        self.addheader(('Content-length', str(len(self.response))))
        self.start_response(self.status, self.response_headers)
        return [self.response]

    def addheader(self, header):
        self.response_headers.append(header)
        
    def extract_args(self):
        qs = self.environ.get('QUERY_STRING','')
        args = {}
        if qs:
            qs = qs.split("&")
            for arg in qs:
                args[arg.split("=")[0]] = arg.split("=")[1]
        return args