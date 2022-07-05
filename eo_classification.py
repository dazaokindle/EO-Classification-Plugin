# -*- coding: utf-8 -*-
"""
/***************************************************************************
 EO_Classfication
                                 A QGIS plugin
 This plugin classifies the raster layers
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-05-09
        git sha              : $Format:%H$
        copyright            : (C) 2022 by Xu Qiongjie
        email                : qiongjie.xu@mail.polimi.it
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import math

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QListWidget, QListWidgetItem

from qgis.core import (
    Qgis,
    QgsProject,
    QgsMessageLog,
    QgsRasterLayer,
)

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .eo_classification_dialog import EO_ClassficationDialog
import os.path

import numpy as np
from .classification import hierarchical, optimization, distance

try:
    from osgeo import gdal
    from osgeo import gdalnumeric
    from osgeo import gdal_array
    from osgeo import osr
except ImportError:
    import gdal

NODATA = -9999


class EO_Classfication:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'EO_Classfication_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&EarthObservation Classification')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        # input raster layer
        self.RASTER_DS = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('EO_Classfication', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/eo_classification/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Simple image classification tool'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&EarthObservation Classification'),
                action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = EO_ClassficationDialog()

            # initial
            self.populate_input_file_combobox()

            # click the button and select the input/output
            self.dlg.input_more_btn.clicked.connect(self.select_input_file)
            self.dlg.output_more_btn.clicked.connect(self.select_output_file)

            # click the button to load input layer
            self.dlg.load_raster_btn.clicked.connect(self.load_raster)
            # click the button to run the classification
            self.dlg.do_classify_btn.clicked.connect(self.unsupervised_classification)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass

    # populate the comboBox for input file with the current loaded layers
    def populate_input_file_combobox(self):
        # the current loaded layers
        for layer in QgsProject.instance().mapLayers().values():
            # populate
            self.dlg.comboBox_input_raster.addItem(layer.name())

    # set input file from folders
    def select_input_file(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg,
        )
        QgsMessageLog.logMessage("Input file {} is selected".format(filename), level=Qgis.Info)
        self.dlg.comboBox_input_raster.addItem(filename)
        self.dlg.comboBox_input_raster.setCurrentText(filename)

    # set output file
    def select_output_file(self):
        filename, _filter = QFileDialog.getOpenFileName(
            self.dlg,
        )
        QgsMessageLog.logMessage("Output file {} is selected".format(filename), level=Qgis.Info)
        self.dlg.lineEdit_output.setText(filename)

    # read input
    # ref: https://automating-gis-processes.github.io/2016/Lesson7-read-raster-array.html
    def load_raster(self):
        if self.RASTER_DS:
            # TODO: deal with opened raster layer
            pass

        # input file name
        path = self.dlg.comboBox_input_raster.currentText()

        if os.path.split(path)[0]:
            self.RASTER_DS = gdal.Open(path)
        else:  # from iface
            rlayer = QgsProject.instance().mapLayersByName(path)[0]
            self.RASTER_DS = gdal.Open(rlayer.dataProvider().dataSourceUri())

        self.dlg.log_area.insertPlainText("Layer {} is open, band count: {}\n".format(path, self.RASTER_DS.RasterCount))

        # show band information to select, default, all bands are selected
        band_statistics = ""
        for i in range(1, self.RASTER_DS.RasterCount + 1):
            item = QListWidgetItem("Band %i" % i)
            self.dlg.list_bands.addItem(item)

            band = self.RASTER_DS.GetRasterBand(i)
            # compute statistics if needed
            if band.GetMinimum() is None or band.GetMaximum() is None:
                band.ComputeStatistics(0)
            
            # fetch metadata for the band
            band.GetMetadata()

            band_statistics += """Band {}:
                [Data Type] = {}
                [NO Data Value] = {}
                [Min] = {}, [Max] = {}

            """.format(
                i,
                gdal.GetDataTypeName(band.DataType),
                band.GetNoDataValue(),
                band.GetMinimum(), band.GetMaximum()
            )

        # show layer properties
        self.dlg.layer_info_browser.append("""Dimensions:
    x size = {},
    y size = {}
        
Metdata:
    {}
        
Number of bands: {}
    {}

Projection: 
    {}
        """.format(
            self.RASTER_DS.RasterXSize, self.RASTER_DS.RasterYSize,
            self.RASTER_DS.GetMetadata(),
            self.RASTER_DS.RasterCount,
            band_statistics,
            self.RASTER_DS.GetProjection()
        ))

    # load configuration for classification methods
    def load_classify_config(self):
        # output file name
        outname = self.dlg.lineEdit_output.text()

        # precision
        precision = self.dlg.lineEdit_precision.text()
        if precision: precision = float(precision)
        # number of cluster
        k_cluster = self.dlg.lineEdit_kcluster.text()
        if k_cluster: k_cluster = int(k_cluster)
        
        # use what method to calculate the distance between points
        point_distance_method = self.dlg.comboBox_point_dist.currentText()

        # classification algorithm
        alg_name = self.dlg.comboBox_algorithm.currentText()
        alg_idx = self.dlg.comboBox_algorithm.currentIndex()

        self.dlg.log_area.insertPlainText("""Classification algorithm: {} (index={})
                point distance method: {}
                precision: {},
                number of cluster: {},
            Output file: {}\n""".format(alg_name, alg_idx, point_distance_method, precision, k_cluster, outname))

        return {
            "precision": precision,
            "k_cluster": k_cluster,
            "point_distance_method": point_distance_method,
            "alg_name": alg_name,
            "alg_idx": alg_idx,
            "outname": outname,
        }

    # transfer raster to a numpy array
    def raster_to_array(self, dtype="int"):
        #bands = [self.RASTER_DS.GetRasterBand(i) for i in range(1, self.RASTER_DS.RasterCount + 1)]

        items = self.dlg.list_bands.selectedItems()

        bands = []
        bands_num = []
        for i in range(len(items)):
            band = int(str(items[i].text()).split("Band ")[-1])
            bands.append(self.RASTER_DS.GetRasterBand(band))
            bands_num.append(band)

        data = np.array([
            gdalnumeric.BandReadAsArray(band) for band in bands
        ]).astype(dtype)

        self.dlg.log_area.insertPlainText("selected band: {}\nRaster -> numpy.array, shape: {}\n".format(bands_num, data.shape))

        return data  # shape:(bands, Y, X)

    # read
    # TODO: write classfied result to raster
    # ref: https://gis.stackexchange.com/questions/34082/creating-raster-layer-from-numpy-array-using-pyqgis
    # data: a numpy array, (x, y) = data.shape
    def write_array_to_raster(self, data, save_to, geotransform, SRID=4326):
        driver = gdal.GetDriverByName('GTiff')

        rows, cols = data.shape
        dataset = driver.Create(
            save_to,
            cols, rows,
            1, gdal.GDT_Float32,
        )

        dataset.SetGeoTransform(geotransform)

        out_srs = osr.SpatialReference()
        out_srs.ImportFromEPSG(SRID)

        dataset.SetProjection(out_srs.ExportToWkt())
        dataset.GetRasterBand(1).WriteArray(data.T)
        dataset.GetRasterBand(1).SetNoDataValue(NODATA)

    # TODO： write resulted n array to raster with original data reserved
    # ref: https://gis.stackexchange.com/questions/318050/writing-numpy-arrays-to-irregularly-shaped-multiband-raster
    def write_array_to_raster_multiband(self, data, save_to,
                                        xres, yres,
                                        xmin, ymin,
                                        nrows, ncols,
                                        ncels, nbands
                                        ):
        cells = np.random.choice(np.arange(nrows * ncols), ncels, replace=False)
        lats = np.arange(ymin, ymin + nrows * yres, yres)
        lons = np.arange(xmin, xmin + ncols * xres, xres)
        lats, lons = np.meshgrid(lats, lons)
        lats, lons = lats.ravel()[cells]
        # make an empty 1 band array to fill with labels
        array = np.empty((nrows, ncols), dtype=np.int)
        xmin, ymin, xmax, ymax = [lons.min(), lats.min(), lons.max(), lats.max()]
        geotransform = (xmin, xres, 0, ymax, 0, -yres)

        # open the file
        out_raster = gdal.GetDriverByName('GTiff'). \
            Create(save_to, ncols, nrows, nbands, gdal.GDT_Float32)
        out_raster.SetGeoTransform(geotransform)

        # Loop bands
        for i in range(nbands):
            # Init array with nodata
            array[:] = NODATA
            # loop lat/lons inc. index j
            for j, (lon, lat) in enumerate(zip(lons, lats)):
                # calc x, y pixel index
                x = math.floor((lon - xmin) / xres)
                y = math.floor((lat - ymin) / xres)
                # TODO: fill the array

            out_raster.GetRasterBand(i + 1).WriteArray(array)
            out_raster.GetRasterBand(i + 1).SetNoDataValue(NODATA)

        del out_raster

    
    def unsupervised_classification(self):
        # change to "log" tab
        self.dlg.classify_tabs.setCurrentIndex(3)

        data = self.raster_to_array()
        (nband, nY, nX) = data.shape
        data = data.reshape((nband, nY*nX)).reshape((nY*nX, nband))

        params = self.load_classify_config()

        algorithms = {
            0: optimization.FUZZY,
            1: hierarchical.DIANA,
        }
        cls = None

        point_distance_methods = {
            "euclidean distance": distance.euclidean_distance,
            "cityblock distance": distance.cityblock_distance,
        }

        #data = self._transfer_data_with_coordinate(data)
        
        #self.dlg.log_area.insertPlainText("after transfer data to 2D with coordiantes, shape: {}".format(data.shape))

        if params["alg_idx"] == 0:
            labels, _ = optimization.FUZZY(data, params["k_cluster"], params["precision"])
        elif params["alg_idx"] == 1:
            labels = hierarchical.DIANA(data, point_distance_methods[params["point_distance_method"]])

        save_data = labels[:, -1].reshape((nX, nY))
        
        
        #if params["alg_idx"] in [0, 1]:
        #    save_data = self._clses_2D_label(cls, data.shape[1:])
        #if params["alg_idx"] in [2]:
        #    save_data = self._cls_2D_label(cls, data.shape[1:])
        
         # save to raster file
        self.write_array_to_raster(save_data, params["outname"], self.RASTER_DS.GetGeoTransform)


    # TODO: transfer data with label into a numpy array
    # whose index corresponding to coordinates and value to class (result[i,j]=label)
    def _cls_2D_label(self, cls, shape):
        result = np.ones(shape) * NODATA
        for ele in cls:
            result[ele[-2], ele[-3]] = ele[-1]
        return result


