"""**archivesspace** is a python module for making queries to ArchivesSpace much easier.

This code lives at: https://github.com/SmithCollegeLibraries/archivesspace-python

Documentation located here: https://smithcollegelibraries.github.io/archivesspace-python/

Compatibility
-------------
As of writing, **archivesspace** has only been tested with ArchivesSpace 2.1.2 and Python 3.
YMMV with other versions.

Getting started
------------------------------------------------------
At the heart of the module is the class `ArchivesSpace`. To set up a connection
create an `ArchivesSpace` with your login credentials, and run the `connect()`
method.

>>> from archivesspace import ArchivesSpace
>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> 
>>> aspace.connect()
>>> print(aspace.connection['user']['username'])
admin

To continue you will first need to familiarize yourself with the ArchivesSpace
REST API documentation located here:
https://archivesspace.github.io/archivesspace/api/#archivesspace-rest-api

    Pro tip: If fields are missing from the API documentation, get them
    from the horse's mouth by checking the ArchivesSpace JSON Schemas located
    here:
    https://github.com/archivesspace/archivesspace/blob/master/common/schemas

    Note that required fields are indicated by "ifmissing" *not* "required."


Getting a record
-----------------
To retrieve a record from ArchivesSpace use the get() method.

>>> from archivesspace import ArchivesSpace
>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> aspace.connect()
>>> jsonResponse = aspace.get("/users/1")
>>> jsonResponse['username']
'admin'


Posting a record
-----------------
To post a record to ArchivesSpace use the `post()` method.

Example:

>>> from archivesspace import ArchivesSpace
>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> aspace.connect()
>>> 
>>> data = { "jsonmodel_type":"subject",
...         "external_ids":[],
...         "publish":True,
...         "used_within_repositories":[],
...         "used_within_published_repositories":[],
...         "terms":[{ "jsonmodel_type":"term",
...         "term":"Alberta",
...         "term_type":"geographic",
...         "vocabulary":"/vocabularies/1"}],
...         "external_documents":[],
...         "vocabulary":"/vocabularies/1",
...         "authority_id":"myid114",
...         "source":"local"}
>>> 
>>> response = aspace.post("/subjects", data)
>>> # import pdb; pdb.set_trace()
>>> response['uri']
'/subjects/...'

Updating a record
-------------------
Upading a record in ArchivesSpace is a two step process. First, retrieve the
record, then post the modified version back to ArchivesSpace.

>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> aspace.connect()
>>> myrecord = aspace.get('/subjects/1')
>>> myrecord['scope_note'] = "Hello World"
>>> response = aspace.post('/subjects/1', requestData=myrecord)
>>> response['lock_version']
1

    Behind the scenes: there's a special field called `lock_version` included in the
    retrieved data structure. This field is required by ArchivesSpace when
    you post the record back. This field ensures that only one agent edits the
    record at a time.


Deleting a record
-------------------
You may find you wish to Delete a record. 

>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> aspace.connect()
>>> data = { "jsonmodel_type":"subject",
...         "external_ids":[],
...         "publish":True,
...         "used_within_repositories":[],
...         "used_within_published_repositories":[],
...         "terms":[{ "jsonmodel_type":"term",
...         "term":"Corie Marshall",
...         "term_type":"topical",
...         "vocabulary":"/vocabularies/1"}],
...         "external_documents":[],
...         "vocabulary":"/vocabularies/1",
...         "authority_id":"myid1a",
...         "source":"local"}
>>> 
>>> response = aspace.post("/subjects", requestData=data)
>>> uri = response['uri']
>>> jsonResponse = aspace.delete(uri)
>>> jsonResponse['status']
'Deleted'


Getting listings and search results
-----------------------------------
ArchivesSpace uses *paginated* responses for queries that would return many items.
To do a paginated query use the `getPaged()` method.

>>> from archivesspace import ArchivesSpace
>>> aspace = ArchivesSpace()
>>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
>>> aspace.connect()
>>> response = aspace.getPaged("/subjects")
>>> for subject in response:
...     print(subject['title'])
... 
Alberta

Reference
---------
"""
import requests
from string import Template
import json
import logging
import pprint
import configparser

logging.getLogger("requests").setLevel(logging.WARNING)

# Custom Error classes
class ConnectionError(Exception):
    pass
class BadRequestType(Exception):
    pass
class NotPaginated(Exception):
    pass
class AspaceBadRequest(Exception):
    def __init__(self, requestdata, response):
        self.requestdata = requestdata
        self.response = response
    def __str__(self):
        return "ASpace Bad Request 400 %s \nRequest data '%s'" % (formatResponse(self.response), formatJson(self.requestdata))
class AspaceForbidden(Exception):
    pass
class AspaceNotFound(Exception):
    pass
class AspaceError(Exception):
    pass

def formatJson(data):
    "Use this function to make data look nice"
    return json.dumps(data, indent=4)

def formatResponse(response):
    "Get the data element of a requests response and format it to be pretty"
    return formatJson(response.json())
    
def logResponse(response):
    logging.error('Response: ' + formatResponse(response))

def checkStatusCodes(response, data={}):
    """This helper function checks the response from a request for problems and then
    returns the data if everything is fine.
    """
    if response.status_code == 403:
        logging.error("Forbidden -- check your credentials.")
        logResponse(response)
        raise AspaceForbidden
    elif response.status_code == 400:
#        logResponse(response)
        raise AspaceBadRequest(data, response)
    elif response.status_code == 404:
        logging.error("Not Found.")
        logResponse(response)
        raise AspaceNotFound
    elif response.status_code == 500:
        logging.error("500 Internal Server Error")
        logResponse(response)
        raise AspaceError
    elif response.status_code == 200:
        return response.json()
    else:
        logging.error(str(response.status_code))
        logResponse(response)
        raise AspaceError

def _unionRequestData(defaultRequestData, newRequestData):
    """Merge default request data and any data passed to the method into one
    unified set of data values to pass to ASpace for the request. Passed data
    overrides default data.
    
    >>> unionedData = _unionRequestData({"foo": "bar"}, {"hello": "world"})
    >>> unionedData['foo']
    'bar'
    >>> unionedData['hello']
    'world'
    >>> _unionRequestData({"foo": "bar"}, {"foo": "world"})
    {'foo': 'world'}
    >>> 
    """

    data = {}

    passedData = ""
    try:
        passedData = newRequestData
    except:
        pass

    # Merge
    data.update(defaultRequestData)
    data.update(passedData)
    return data

class ArchivesSpace(object):
    """Base class for establishing a session with an ArchivesSpace repository,
    and doing API queries against it.
    
    >>> from archivesspace import ArchivesSpace
    >>> aspace = ArchivesSpace()
    >>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
    >>> aspace.connect()
    >>> print(aspace.connection['user']['username'])
    admin
    """
    
    # Optional custom JSON serializer to be passed to json.dumps if provided
    # See method ArchivesSpace.setJsonSerializerDefault()
    jsonSerializerDefault = None
    
    def __init__(self):
        self.configData = configparser.ConfigParser()
        self.serverConfig = None
        self.session = None

    def setServer(self, protocol, domain, port, username, password, path=""):
        self.protocol = protocol
        self.domain = domain
        self.port = port
        self.path = path
        self.username = username
        self.password = password

    def setServerCfg(self, fileName, section="DEFAULT"):
        try:
            self.configData.read_file(open(fileName), source=fileName)
        except FileNotFoundError:
            logging.error('No configuration file found. Configuration file required. Please copy archivesspace-example.cfg to %s and edit.' % fileName)
            exit(1)

        try:
            self.serverConfig = self.configData[section]
        except KeyError:
            print("'%s' section not present in configuration file %s" % (section, fileName))
            exit(1)

        try:
            self.setServer(self.serverConfig['protocol'], self.serverConfig['hostname'], self.serverConfig['port'], self.serverConfig['username'], self.serverConfig['password'], path=self.serverConfig['path'])
        except KeyError as e:
            print("Missing configuration option %s" % e)
            exit(1)
            
    def _getHost(self):
        """Returns the host string containing the protocol domain name and port."""
        hostTemplate = Template('$protocol://$domain:$port/$path')
        return hostTemplate.substitute(protocol = self.protocol, domain = self.domain, port = self.port, path = self.path)

    def _request(self, path, type, data):
        # Send the request
        datajson = ''
        try:
            if type == "post":
                if self.jsonSerializerDefault is not None:
                    datajson = json.dumps(data, default = self.jsonSerializerDefault) # turn the data into json format for POST requests
                else:
                    datajson = json.dumps(data) # turn the data into json format for POST requests
                r = self.session.post(self._getHost() + path, data = datajson)
            elif type == "get":
                r = self.session.get(self._getHost() + path, data = data)
            elif type == "delete":
                r = self.session.delete(self._getHost() + path, data = data)
            else:
                raise BadRequestType
            
        except requests.exceptions.ConnectionError:
            logging.error('Unable to connect to ArchivesSpace. Check the host information.')
            raise ConnectionError
        else:
            jsonResponse = checkStatusCodes(r, data=data)
            return jsonResponse

    def post(self, path, requestData={}):
        """Do a POST request to ArchivesSpace and return the JSON response

        >>> from archivesspace import ArchivesSpace
        >>> aspace = ArchivesSpace()
        >>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
        >>> aspace.connect()
        >>> 
        >>> data = { "jsonmodel_type":"subject",
        ...         "external_ids":[],
        ...         "publish":True,
        ...         "used_within_repositories":[],
        ...         "used_within_published_repositories":[],
        ...         "terms":[{ "jsonmodel_type":"term",
        ...         "term":"North Pole",
        ...         "term_type":"geographic",
        ...         "vocabulary":"/vocabularies/1"}],
        ...         "external_documents":[],
        ...         "vocabulary":"/vocabularies/1",
        ...         "authority_id":"myid314",
        ...         "source":"local"}
        >>> 
        >>> response = aspace.post("/subjects", requestData=data)
        >>> response['uri']
        '/subjects/...'
        >>> 
        """
        data = ""
        try:
            data = requestData
        except e:
            raise e
        return self._request(path, 'post', data)

    def get(self, path, requestData={}):
        """Do a GET request to ArchivesSpace and return the JSON response
        
        >>> from archivesspace import ArchivesSpace
        >>> aspace = ArchivesSpace()
        >>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
        >>> aspace.connect()
        >>> jsonResponse = aspace.get("/users/1")
        >>> jsonResponse['username']
        'admin'
        """
        data = ""
        try:
            data = requestData
        except:
            pass
        return self._request(path, 'get', data)

    def delete(self, path, requestData={}):
        """Do a DELETE request to ArchivesSpace and return the JSON repsonse

        >>> from archivesspace import ArchivesSpace
        >>> aspace = ArchivesSpace()
        >>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
        >>> aspace.connect()
        >>> data = { "jsonmodel_type":"subject",
        ...         "external_ids":[],
        ...         "publish":True,
        ...         "used_within_repositories":[],
        ...         "used_within_published_repositories":[],
        ...         "terms":[{ "jsonmodel_type":"term",
        ...         "term":"Claire Marshall",
        ...         "term_type":"topical",
        ...         "vocabulary":"/vocabularies/1"}],
        ...         "external_documents":[],
        ...         "vocabulary":"/vocabularies/1",
        ...         "authority_id":"myid73",
        ...         "source":"local"}
        >>> 
        >>> response = aspace.post("/subjects", requestData=data)
        >>> uri = response['uri']
        >>> jsonResponse = aspace.delete(uri)
        >>> jsonResponse['status']
        'Deleted'
        """        
        data = ""
        try: 
            data = requestData
        except:
            pass
        return self._request(path, 'delete', data)
        
    def connect(self):
        """Start a sessions with ArchivesSpace. This must be done before anything else.

        >>> from archivesspace import ArchivesSpace
        >>> aspace = ArchivesSpace()
        >>> aspace.setServer('http', 'localhost', '8089', 'admin', 'admin')
        >>> aspace.connect()
        >>> print(aspace.connection['user']['username'])
        admin
        """
        pathTemplate = Template('/users/$username/login')
        path = pathTemplate.substitute(username = self.username)

        # Use the requests Session class to handle the session
        # http://docs.python-requests.org/en/master/user/advanced/#session-objects
        self.session = requests.Session()

        try:
            response = self.session.post(self._getHost() + path, { "password" : self.password })
            jsonResponse = checkStatusCodes(response)
        except requests.exceptions.ConnectionError:
            logging.error("Connection Error.")
            exit(1)
        else:
            self.connection = jsonResponse # Save connection details as python data
            self.sessionId = self.connection['session']
            self.session.headers.update({ 'X-ArchivesSpace-Session' : self.sessionId })

    def getPaged(self, path, requestData={}):
        """Automatically request all the pages to build a complete data set"""

        requestData = _unionRequestData({"page": "1"}, requestData)
        # Start a place to add the pages to as they come in
        fullSet = []
        # Get the first page
        response = self.get(path, requestData=requestData)
        # Start the big data set
        try:
            fullSet = response['results']
        except KeyError:
            raise NotPaginated
        # Then determine how many pages there are
        numPages = response['last_page']
        # Loop through all the pages and append them to a single big data structure
        for page in range(1, numPages):
            requestDataPaginated = _unionRequestData(requestData, {"page": str(page)})
            response = self.get(path, requestData=requestDataPaginated)
            fullSet.extend(response['results'])
        # Return the big data structure
        return fullSet

    def getPagedAllIds(self, path):
        """Get a list of all of the IDs"""
        response = self.get(path, requestData={"all_ids": True})
        # Expecting a list of ints, if it's not there's problem
        if all(isinstance(item, int) for item in response):
            return response
        else:
            raise NotPaginated

    def setJsonSerializerDefault(self, jsonSerializerDefault):
        """Set an optional custom JSON serializer to be passed to json.dumps.
        c.f.
        https://docs.python.org/3/library/json.html#json.JSONEncoder.default
        
        If you don't know what this is, don't use it.
        """
        self.jsonSerializerDefault = jsonSerializerDefault

if __name__ == "__main__":
    import doctest
    print("Running tests...")
    
    doctest.testmod(optionflags=doctest.ELLIPSIS, verbose=True)
