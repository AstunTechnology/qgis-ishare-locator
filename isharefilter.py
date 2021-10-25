# -*- coding: utf-8 -*-
from qgis.core import Qgis, QgsMessageLog, QgsLocatorFilter, QgsLocatorResult, QgsRectangle, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsPointXY
from qgis.gui import QgsVertexMarker
from . networkaccessmanager import NetworkAccessManager, RequestsException
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
import json
import time
from requests.models import PreparedRequest


class iShareFilterPlugin:

    def __init__(self, iface):

        self.iface = iface

        self.filter = iShareLocatorFilter(self.iface)

        # THIS is not working?? As in show_problem never called
        self.filter.resultProblem.connect(self.show_problem)
        self.iface.registerLocatorFilter(self.filter)

    def show_problem(self, err):
        self.filter.info("showing problem???")  # never come here?
        self.iface.messageBar().pushWarning(
            "iShareLocatorFilter Error", '{}'.format(err))

    def initGui(self):
        pass

    def unload(self):
        self.iface.deregisterLocatorFilter(self.filter)
        # self.filter.resultProblem.disconnect(self.show_problem)


# SEE: https://github.com/qgis/QGIS/blob/master/src/core/locator/qgslocatorfilter.h
#      for all attributes/members/functions to be implemented
class iShareLocatorFilter(QgsLocatorFilter):

    USER_AGENT = b'Mozilla/5.0 QGIS iShareLocatorFilter'

    url = "https://mapping.milton-keynes.gov.uk/getdata.aspx"
    params = {
        'type': 'json',
        'RequestType': 'LocationSearch',
        'gettotals': 'true',
        'axuid': '1629885379107',
        'mapsource': 'mapsources/MyHouse',
        '_': '1629885379107',
        'pagesize': '50',
        'startnum': '1'
    }
    req = PreparedRequest()
    new_url = req.prepare_url(url, params)
    SEARCH_URL = req.url+'&location='
     
    #SEARCH_URL = 'https://mapping.milton-keynes.gov.uk/getdata.aspx?type=json&service=LocationSearch&RequestType=LocationSearch&pagesize=25&startnum=1&gettotals=false&axuid=1629885379107&mapsource=mapsources/MyHouse&_=1629885379107&location='

    # some magic numbers to be able to zoom to more or less defined levels
    ADDRESS = 1000
    STREET = 1500
    ZIP = 3000
    PLACE = 30000
    CITY = 120000
    ISLAND = 250000
    COUNTRY = 4000000

    resultProblem = pyqtSignal(str)

    def __init__(self, iface):
        # you REALLY REALLY have to save the handle to iface, else segfaults!!
        self.iface = iface
        super(QgsLocatorFilter, self).__init__()

    def name(self):
        return self.__class__.__name__

    def clone(self):
        return iShareLocatorFilter(self.iface)

    def displayName(self):
        return 'iShare Gazetteer'

    def prefix(self):
        return 'gaz'

    def fetchResults(self, search, context, feedback):

        if len(search) < 2:
            return

        # see https://operations.osmfoundation.org/policies/nominatim/
        # "Auto-complete search This is not yet supported by iShare and you must not implement such a service on the client side using the API."
        # so end with a space to trigger a search:
        # if search[-1] != ' ':
        #    return

        url = '{}{}'.format(self.SEARCH_URL, search)
        self.info('Search url {}'.format(url))
        nam = NetworkAccessManager()
        try:
            # see https://operations.osmfoundation.org/policies/nominatim/
            # "Provide a valid HTTP Referer or User-Agent identifying the application (QGIS geocoder)"
            headers = {b'User-Agent': self.USER_AGENT}
            # use BLOCKING request, as fetchResults already has it's own thread!
            (response, content) = nam.request(
                url, headers=headers, blocking=True)
            # self.info(response)
            # self.info(response.status_code)
            if response.status_code == 200:  # other codes are handled by NetworkAccessManager
                text = content.decode('utf-8')
                data = json.loads(text)
                columns = data['columns']
                for item in data['data']:
                    mapped = dict(zip(columns, item))
                    #result = namedtuple('Result', ['description', 'x', 'y'])
                    result = QgsLocatorResult()
                    result.filter = self
                    result.displayString = mapped['Name']
                    # use the json full item as userData, so all info is in it:
                    result.userData = mapped
                    self.resultFetched.emit(result)

        except RequestsException as err:
            # Handle exception..
            # only this one seems to work
            self.info(err)
            # THIS: results in a floating window with a warning in it, wrong thread/parent?
            #self.iface.messageBar().pushWarning("iShareLocatorFilter Error", '{}'.format(err))
            # THIS: emitting the signal here does not work either?
            self.resultProblem.emit('{}'.format(err))

    def remove_marker(self):
        vertex_items = [ i for i in self.iface.mapCanvas().scene().items() if issubclass(type(i), QgsVertexMarker)]
        for ver in vertex_items:
            if ver in self.iface.mapCanvas().scene().items():
                self.iface.mapCanvas().scene().removeItem(ver)

    def triggerResult(self, result):
        self.info("UserClick: {}".format(result.displayString))
        doc = result.userData
        x = doc['X']
        y = doc['Y']
        rect = QgsRectangle(float(x), float(y), float(x), float(y))
        dest_crs = QgsProject.instance().crs()
        results_crs = QgsCoordinateReferenceSystem(
            27700, QgsCoordinateReferenceSystem.PostgisCrsId)
        transform = QgsCoordinateTransform(
            results_crs, dest_crs, QgsProject.instance())
        r = transform.transformBoundingBox(rect)
        self.iface.mapCanvas().setExtent(r, False)
        self.iface.mapCanvas().zoomScale(1000)
        self.iface.mapCanvas().refresh()

        canvas = self.iface.mapCanvas()
        self.remove_marker()
        easting = int(float(x))
        northing =int(float(y))
        pnt = QgsPointXY(easting,northing)
        self.m = QgsVertexMarker(canvas)
        self.m.setCenter(pnt)
        self.m.setColor(QColor('Black'))
        self.m.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.m.setIconSize(12)
        self.m.setPenWidth(1)
        self.m.setFillColor(QColor(200,0,0))
        self.m.hide()
        self.m.show()

    def info(self, msg=""):
        QgsMessageLog.logMessage('{} {}'.format(
            self.__class__.__name__, msg), 'iShareLocatorFilter', Qgis.Info)
