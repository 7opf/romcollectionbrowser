import xbmc, xbmcgui, xbmcaddon
import time, os

from util import *
import util
import helper, config
import dialogprogress
from config import *
from gamedatabase import *

#Action Codes
# See guilib/Key.h
ACTION_CANCEL_DIALOG = (9, 10, 51, 92, 110, 122)
ACTION_MOVEMENT_LEFT = (1,)
ACTION_MOVEMENT_RIGHT = (2,)
ACTION_MOVEMENT_UP = (3,)
ACTION_MOVEMENT_DOWN = (4,)
ACTION_MOVEMENT = (1, 2, 3, 4, 5, 6, 159, 160)
ACTION_INFO = (11,)
ACTION_CONTEXT = (117,)

#ControlIds
CONTROL_CONSOLES = 500
CONTROL_GENRE = 600
CONTROL_YEAR = 700
CONTROL_PUBLISHER = 800
CONTROL_CHARACTER = 900
FILTER_CONTROLS = (500, 600, 700, 800, 900,)
GAME_LISTS = (50, 51, 52, 53, 54, 55, 56, 57, 58)
CONTROL_SCROLLBARS = (2200, 2201, 60, 61, 62, 67)

CONTROL_GAMES_GROUP_START = 50
CONTROL_GAMES_GROUP_END = 59

CONTROL_BUTTON_CHANGE_VIEW = 2
CONTROL_BUTTON_FAVORITE = 1000
CONTROL_BUTTON_SEARCH = 1100
NON_EXIT_RCB_CONTROLS = (500, 600, 700, 800, 900, 2, 1000, 1100)

CONTROL_LABEL_MSG = 4000
CONTROL_BUTTON_MISSINGINFODIALOG = 4001


class MyPlayer(xbmc.Player):
    gui = None

    def onPlayBackEnded(self):
        xbmc.log('RCB MyPlayer: onPlaybackEnded')

        if self.gui == None:
            print "RCB_WARNING: gui == None in MyPlayer"
            return

        self.gui.setFocus(self.gui.getControl(CONTROL_GAMES_GROUP_START))


class UIGameDB(xbmcgui.WindowXML):
    gdb = None

    selectedControlId = 0
    selectedConsoleId = 0
    selectedGenreId = 0
    selectedYearId = 0
    selectedPublisherId = 0
    selectedCharacter = util.localize(32120)

    selectedConsoleIndex = 0
    selectedGenreIndex = 0
    selectedYearIndex = 0
    selectedPublisherIndex = 0
    selectedCharacterIndex = 0

    applyFilterThread = None
    applyFilterThreadStopped = False
    applyFiltersInProgress = False

    filterChanged = False

    #last selected game position (prevent invoke showgameinfo twice)
    lastPosition = -1

    #dummy to be compatible with ProgressDialogGUI
    itemCount = 0

    # set flag if we opened GID
    gameinfoDialogOpen = False

    searchTerm = ''

    def __init__(self, strXMLname, strFallbackPath, strDefaultName, forceFallback, isMedia=True):
        Logutil.log("Init Rom Collection Browser: " + util.RCBHOME, util.LOG_LEVEL_INFO)

        addon = xbmcaddon.Addon(id='%s' % util.SCRIPTID)
        Logutil.log("RCB version: " + addon.getAddonInfo('version'), util.LOG_LEVEL_INFO)

        # Check if RCB service is available
        try:
            serviceAddon = xbmcaddon.Addon(id=util.SCRIPTID)
            Logutil.log("RCB service addon: " + str(serviceAddon), util.LOG_LEVEL_INFO)
        except:
            Logutil.log("No RCB service addon available.", util.LOG_LEVEL_INFO)

        self.initialized = False
        self.Settings = util.getSettings()

        # Make sure that we don't start RCB in cycles
        self.Settings.setSetting('rcb_launchOnStartup', 'false')

        # Check if background game import is running
        if self.checkUpdateInProgress():
            self.quit = True
            return

        # timestamp1 = time.clock()

        self.quit = False

        self.config, success = self.initializeConfig()
        if not success:
            self.quit = True
            return

        success = self.initializeDataBase()
        if not success:
            self.quit = True
            return

        #load video fileType for later use in showGameInfo
        self.fileTypeGameplay, errorMsg = self.config.get_filetype_by_name('gameplay', self.config.tree)
        if self.fileTypeGameplay == None:
            Logutil.log("Error while loading fileType gameplay: " + errorMsg, util.LOG_LEVEL_WARNING)

        #load fileType clearlogo for later use in showGameInfo
        self.fileTypeClearlogo, errorMsg = self.config.get_filetype_by_name('clearlogo', self.config.tree)
        if self.fileTypeClearlogo == None:
            Logutil.log("Error while loading fileType gameplay: " + errorMsg, util.LOG_LEVEL_WARNING)

        #timestamp2 = time.clock()
        #diff = (timestamp2 - timestamp1) * 1000
        #print "RCB startup time: %d ms" % (diff)

        self.player = MyPlayer()
        self.player.gui = self

        self.initialized = True

    # FIXME TODO Move to config.py
    def initializeConfig(self):
        Logutil.log("initializeConfig", util.LOG_LEVEL_INFO)

        config = Config(None)
        createNewConfig = False

        #check if we have config file
        configFile = util.getConfigXmlPath()
        if not os.path.isfile(configFile):
            Logutil.log("No config file available. Create new one.", util.LOG_LEVEL_INFO)
            dialog = xbmcgui.Dialog()
            createNewConfig = dialog.yesno(util.SCRIPTNAME, util.localize(32100), util.localize(32101))
            if not createNewConfig:
                return config, False
        else:
            rcAvailable, message = config.checkRomCollectionsAvailable()
            if not rcAvailable:
                Logutil.log("No Rom Collections found in config.xml.", util.LOG_LEVEL_INFO)
                dialog = xbmcgui.Dialog()
                createNewConfig = dialog.yesno(util.SCRIPTNAME, util.localize(32100), util.localize(32101))
                if not createNewConfig:
                    return config, False

        if createNewConfig:
            import wizardconfigxml
            statusOk, errorMsg = wizardconfigxml.ConfigXmlWizard().createConfigXml(configFile)
            if statusOk == False:
                xbmcgui.Dialog().ok(util.SCRIPTNAME, util.localize(32001), errorMsg)
                return config, False
        else:
            from configxmlupdater import *
            #check if config.xml is up to date
            returnCode, message = ConfigxmlUpdater().updateConfig(configFile)
            if returnCode == False:
                xbmcgui.Dialog().ok(util.SCRIPTNAME, util.localize(32001), message)

        #read config.xml
        statusOk, errorMsg = config.readXml()
        if statusOk == False:
            xbmcgui.Dialog().ok(util.SCRIPTNAME, util.localize(32002), errorMsg)

        #set flag if the skin should display clearlogo as title in lists
        if self.Settings.getSetting(util.SETTING_RCB_USECLEARLOGOASTITLE).upper() == "TRUE":
            xbmc.executebuiltin('Skin.SetBool(%s)' % util.SETTING_RCB_USECLEARLOGOASTITLE)
        else:
            xbmc.executebuiltin('Skin.Reset(%s)' % util.SETTING_RCB_USECLEARLOGOASTITLE)

        return config, statusOk

    # FIXME TODO Move to gamedatabase.py
    def initializeDataBase(self):
        try:
            self.gdb = GameDataBase(util.getAddonDataPath())
            self.gdb.connect()
        except Exception, (exc):
            xbmcgui.Dialog().ok(util.SCRIPTNAME, util.localize(32000), str(exc))
            Logutil.log('Error accessing database: ' + str(exc), util.LOG_LEVEL_ERROR)
            return False

        #check if database is up to date
        #create new one or alter existing one
        doImport, errorMsg = self.gdb.checkDBStructure()

        if doImport == -1:
            xbmcgui.Dialog().ok(util.SCRIPTNAME, errorMsg)
            return False

        if doImport == 2:
            xbmcgui.Dialog().ok(util.SCRIPTNAME, util.localize(32102), util.localize(32103))

        self.checkImport(doImport, None, False)
        return True

    def onInit(self):

        Logutil.log("Begin onInit", util.LOG_LEVEL_INFO)

        if self.quit:
            Logutil.log("RCB decided not to run. Bye.", util.LOG_LEVEL_INFO)
            self.close()
            return

        self.clearList()
        xbmc.sleep(util.WAITTIME_UPDATECONTROLS)

        #reset last view
        self.loadViewState()

        Logutil.log("End onInit", util.LOG_LEVEL_INFO)

    def onAction(self, action):

        Logutil.log("onAction: " + str(action.getId()), util.LOG_LEVEL_INFO)

        if action.getId() == 0:
            Logutil.log("actionId == 0. Input ignored", util.LOG_LEVEL_INFO)
            return

        try:
            if action.getId() in ACTION_CANCEL_DIALOG:
                Logutil.log("onAction: ACTION_CANCEL_DIALOG", util.LOG_LEVEL_INFO)

                #don't exit RCB here. Just close the filters
                if self.selectedControlId in NON_EXIT_RCB_CONTROLS:
                    Logutil.log("selectedControl in NON_EXIT_RCB_CONTROLS: %s" % self.selectedControlId,
                                util.LOG_LEVEL_INFO)
                    #HACK: when list is empty, focus sits on other controls than game list
                    if self.getListSize() > 0:
                        self.setFocus(self.getControl(CONTROL_GAMES_GROUP_START))
                        return

                    Logutil.log("ListSize == 0 in onAction. Assume that we have to exit.", util.LOG_LEVEL_WARNING)

                if self.player.isPlayingVideo():
                    self.player.stop()
                    xbmc.sleep(util.WAITTIME_PLAYERSTOP)

                self.exit()
            elif action.getId() in ACTION_MOVEMENT:

                Logutil.log("onAction: ACTION_MOVEMENT", util.LOG_LEVEL_DEBUG)

                control = self.getControlById(self.selectedControlId)
                if control == None:
                    Logutil.log("control == None in onAction", util.LOG_LEVEL_WARNING)
                    return

                if CONTROL_GAMES_GROUP_START <= self.selectedControlId <= CONTROL_GAMES_GROUP_END:
                    #HACK: check last position in list (prevent loading game info)
                    pos = self.getCurrentListPosition()
                    Logutil.log('onAction: current position = ' + str(pos), util.LOG_LEVEL_DEBUG)
                    Logutil.log('onAction: last position = ' + str(self.lastPosition), util.LOG_LEVEL_DEBUG)
                    if pos != self.lastPosition:
                        self.showGameInfo()

                    self.lastPosition = pos

                if self.selectedControlId in FILTER_CONTROLS:

                    """
                    if self.player.isPlayingVideo():
                        self.player.stop()
                        xbmc.sleep(util.WAITTIME_PLAYERSTOP)

                    pos = control.getSelectedPosition()
                    cid = control.getId()
                    if cid == CONTROL_CONSOLES and self.hasConsoleFilterChanged(pos):
                        self.updateSelectedConsole(control)

                    elif cid == CONTROL_GENRE and self.hasGenreFilterChanged(pos):
                        self.updateSelectedGenre(control)

                    elif cid == CONTROL_YEAR and self.hasYearFilterChanged(pos):
                        self.updateSelectedYear(control)

                    elif cid == CONTROL_PUBLISHER and self.hasPublisherFilterChanged(pos):
                        self.updateSelectedPublisher(control)

                    elif cid == CONTROL_CHARACTER and self.hasCharacterFilterChanged(pos):
                        self.updateSelectedCharacter(control)
                    """

            elif action.getId() in ACTION_INFO:
                Logutil.log("onAction: ACTION_INFO", util.LOG_LEVEL_DEBUG)

                control = self.getControlById(self.selectedControlId)
                if control == None:
                    Logutil.log("control == None in onAction", util.LOG_LEVEL_WARNING)
                    return
                if CONTROL_GAMES_GROUP_START <= self.selectedControlId <= CONTROL_GAMES_GROUP_END:
                    self.showGameInfoDialog()
            elif action.getId() in ACTION_CONTEXT:

                if self.player.isPlayingVideo():
                    self.player.stop()
                    xbmc.sleep(util.WAITTIME_PLAYERSTOP)

                self.showContextMenu()

                self.setFocus(self.getControl(CONTROL_GAMES_GROUP_START))

                Logutil.log('onAction: ACTION_CONTEXT', util.LOG_LEVEL_INFO)
        except Exception, (exc):
            Logutil.log("RCB_ERROR: unhandled Error in onAction: " + str(exc), util.LOG_LEVEL_ERROR)

    def onClick(self, controlId):
        log.debug("onClick: {0}".format(controlId))
        if controlId in FILTER_CONTROLS:
            if controlId == CONTROL_CONSOLES:
                consoles = []
                for romCollection in self.config.romCollections.values():
                    consoles.append([romCollection.id, romCollection.name])

                # Sort the consoles by name
                consoles = sorted(consoles, key=lambda console: console[1])
                consoles = [('0', util.localize(32120))] +consoles
                items = []
                for console in consoles:
                    item = xbmcgui.ListItem(console[1])
                    item.setProperty('id', console[0])
                    items.append(item)
                index = xbmcgui.Dialog().select(util.localize(32406), items)
                item = items[index]
                button = self.getControlById(CONTROL_CONSOLES)
                button.setLabel(item.getLabel())
                self.selectedConsoleId = int(item.getProperty('id'))
                self.showGames()
            if controlId == CONTROL_GENRE:
                genres = []
                rows = Genre(self.gdb).getFilteredGenresByConsole(self.selectedConsoleId)
                for row in rows:
                    genres.append([row[Genre.COL_ID], row[Genre.COL_NAME]])

                genres = sorted(genres, key=lambda genre: genre[1])
                genres = [('0', util.localize(32120))] +genres
                items = []
                for genre in genres:
                    item = xbmcgui.ListItem(genre[1])
                    item.setProperty('id', str(genre[0]))
                    items.append(item)
                index = xbmcgui.Dialog().select(util.localize(32401), items)
                item = items[index]
                button = self.getControlById(CONTROL_GENRE)
                button.setLabel(item.getLabel())
                self.selectedGenreId = int(item.getProperty('id'))
                self.showGames()
            if controlId == CONTROL_YEAR:
                years = []
                rows = Year(self.gdb).getFilteredYearsByConsole(self.selectedConsoleId)
                for row in rows:
                    years.append([row[Year.COL_ID], row[Year.COL_NAME]])

                years = sorted(years, key=lambda year: year[1])
                years = [('0', util.localize(32120))] + years
                items = []
                for year in years:
                    item = xbmcgui.ListItem(year[1])
                    item.setProperty('id', str(year[0]))
                    items.append(item)
                index = xbmcgui.Dialog().select(util.localize(32400), items)
                item = items[index]

                button = self.getControlById(CONTROL_YEAR)
                button.setLabel(item.getLabel())
                self.selectedYearId = int(item.getProperty('id'))
                self.showGames()
            if controlId == CONTROL_PUBLISHER:
                publishers = []
                rows = Publisher(self.gdb).getFilteredPublishersByConsole(self.selectedConsoleId)
                for row in rows:
                    publishers.append([row[Publisher.COL_ID], row[Publisher.COL_NAME]])

                publishers = sorted(publishers, key=lambda publisher: publisher[1])
                publishers = [('0', util.localize(32120))] + publishers
                items = []
                for publisher in publishers:
                    item = xbmcgui.ListItem(publisher[1])
                    item.setProperty('id', str(publisher[0]))
                    items.append(item)
                index = xbmcgui.Dialog().select(util.localize(32402), items)
                item = items[index]

                button = self.getControlById(CONTROL_PUBLISHER)
                button.setLabel(item.getLabel())
                self.selectedPublisherId = int(item.getProperty('id'))
                self.showGames()
            if controlId == CONTROL_CHARACTER:
                characters = [util.localize(32120)]
                characters.append('0-9')
                for i in range(0, 26):
                    char = chr(ord('A') + i)
                    characters.append(char)

                index = xbmcgui.Dialog().select('A-Z', characters)

                button = self.getControlById(CONTROL_CHARACTER)
                button.setLabel(characters[index])
                self.selectedCharacter = characters[index]
                self.showGames()
            """
            if self.filterChanged:
                log.debug("onClick: apply Filters")
                self.applyFilters()
                self.filterChanged = False
            else:
                log.debug("onClick: Show Game Info")
                self.setFocus(self.getControl(CONTROL_GAMES_GROUP_START))
                self.showGameInfo()
            """
        elif controlId in GAME_LISTS:
            log.debug("onClick: Launch Emu")
            self.launchEmu()
        elif controlId == CONTROL_BUTTON_FAVORITE:
            log.debug("onClick: Button Favorites")
            self.showGames()
        elif controlId == CONTROL_BUTTON_SEARCH:
            log.debug("onClick: Button Search")

            searchButton = self.getControlById(CONTROL_BUTTON_SEARCH)
            if searchButton is None:
                return

            self.searchTerm = xbmcgui.Dialog().input(util.localize(32116), type=xbmcgui.INPUT_ALPHANUM)
            lbl = util.localize(32117) if self.searchTerm == '' else util.localize(32117) + ': ' + self.searchTerm
            searchButton.setLabel(lbl)

            self.showGames()

        elif controlId == CONTROL_BUTTON_MISSINGINFODIALOG:
            import dialogmissinginfo
            try:
                missingInfoDialog = dialogmissinginfo.MissingInfoDialog("script-RCB-missinginfo.xml",
                                                                        util.getAddonInstallPath(),
                                                                        util.getConfiguredSkin(), "720p", gui=self)
            except:
                missingInfoDialog = dialogmissinginfo.MissingInfoDialog("script-RCB-missinginfo.xml",
                                                                        util.getAddonInstallPath(),
                                                                        "Default", "720p", gui=self)
            if missingInfoDialog.saveConfig:
                self.config.readXml()
                self.showGames()

            del missingInfoDialog

        elif controlId == CONTROL_BUTTON_CHANGE_VIEW:
            # Need to change viewmode manually since Frodo
            xbmc.executebuiltin('Container.NextViewMode')

    def onFocus(self, controlId):
        Logutil.log("onFocus: " + str(controlId), util.LOG_LEVEL_DEBUG)
        self.selectedControlId = controlId

    # Check if one of the filter lists has changed

    def hasConsoleFilterChanged(self, pos):
        return self.selectedConsoleIndex != pos

    def hasGenreFilterChanged(self, pos):
        return self.selectedGenreIndex != pos

    def hasYearFilterChanged(self, pos):
        return self.selectedYearIndex != pos

    def hasPublisherFilterChanged(self, pos):
        return self.selectedPublisherIndex != pos

    def hasCharacterFilterChanged(self, pos):
        return self.selectedCharacterIndex != pos

    # Handle when one of the filter lists has changed

    def updateSelectedConsole(self, control):
        label2 = str(control.getSelectedItem().getLabel2())

        self.selectedConsoleId = int(label2)
        self.selectedConsoleIndex = control.getSelectedPosition()
        self.filterChanged = True

    def updateSelectedPublisher(self, control):
        label2 = str(control.getSelectedItem().getLabel2())

        self.selectedPublisherId = int(label2)
        self.selectedPublisherIndex = control.getSelectedPosition()
        self.filterChanged = True

    def updateSelectedGenre(self, control):
        label2 = str(control.getSelectedItem().getLabel2())

        self.selectedGenreId = int(label2)
        self.selectedGenreIndex = control.getSelectedPosition()
        self.filterChanged = True

    def updateSelectedYear(self, control):
        label2 = str(control.getSelectedItem().getLabel2())

        self.selectedYearId = int(label2)
        self.selectedYearIndex = control.getSelectedPosition()
        self.filterChanged = True

    def updateSelectedCharacter(self, control):
        # Note - different to the others
        label = str(control.getSelectedItem().getLabel())

        self.selectedCharacter = label
        self.selectedCharacterIndex = control.getSelectedPosition()
        log.debug("char is {0}, index is {1}".format(self.selectedCharacter, self.selectedCharacterIndex))
        self.filterChanged = True

    def updateControls(self, onInit):
        log.debug("Begin updateControls")

        # Prepare Filter Controls. If statement takes care of dependencies between each filter control
        if onInit:
            self.showConsoles()
        if onInit or self.selectedControlId == CONTROL_CONSOLES:
            self.showGenre()
        if onInit or self.selectedControlId in [CONTROL_CONSOLES, CONTROL_GENRE]:
            self.showYear()
        if onInit or self.selectedControlId in [CONTROL_CONSOLES, CONTROL_GENRE, CONTROL_YEAR]:
            self.showPublisher()
        if onInit:
            self.showCharacterFilter()

        log.debug("End updateControls")

    def showConsoles(self):
        log.debug("Begin showConsoles")

        self.selectedConsoleId

        """
        showEntryAllItems = getSettings().getSetting(util.SETTING_RCB_SHOWENTRYALLCONSOLES).upper() == 'TRUE'

        consoles = []
        for romCollection in self.config.romCollections.values():
            consoles.append([romCollection.id, romCollection.name])

        # Sort the consoles by name
        consoles = sorted(consoles, key=lambda console: console[1])

        self.showFilterControl(consoles, CONTROL_CONSOLES, showEntryAllItems)

        # Reset selection after loading the list
        self.selectedConsoleId = 0
        self.selectedConsoleIndex = 0
        """

        log.debug("End showConsoles")

    def showGenre(self):
        log.debug("Begin showGenre with selected console {0}".format(self.selectedConsoleId))

        rows = Genre(self.gdb).getFilteredGenresByConsole(self.selectedConsoleId)
        log.debug("Found {0} genres to add to filter list".format(len(rows)))

        showEntryAllItems = getSettings().getSetting(util.SETTING_RCB_SHOWENTRYALLGENRES).upper() == 'TRUE'
        self.showFilterControl(rows, CONTROL_GENRE, showEntryAllItems)

        # Reset selection after loading the list
        self.selectedGenreId = 0
        self.selectedGenreIndex = 0

        log.debug("End showGenre")

    def showYear(self):
        log.debug("Begin showYear with selected console {0}".format(self.selectedConsoleId))

        rows = Year(self.gdb).getFilteredYearsByConsole(self.selectedConsoleId)
        log.debug("Found {0} years to add to filter list".format(len(rows)))

        showEntryAllItems = getSettings().getSetting(util.SETTING_RCB_SHOWENTRYALLYEARS).upper() == 'TRUE'
        self.showFilterControl(rows, CONTROL_YEAR, showEntryAllItems)

        # Reset selection after loading the list
        self.selectedYearId = 0
        self.selectedYearIndex = 0

        log.debug("End showYear")

    def showPublisher(self):
        log.debug("Begin showPublisher with selected console {0}".format(self.selectedConsoleId))

        rows = Publisher(self.gdb).getFilteredPublishersByConsole(self.selectedConsoleId)
        log.debug("Found {0} publishers to add to filter list".format(len(rows)))

        showEntryAllItems = getSettings().getSetting(util.SETTING_RCB_SHOWENTRYALLPUBLISHER).upper() == 'TRUE'
        self.showFilterControl(rows, CONTROL_PUBLISHER, showEntryAllItems)

        # Reset selection after loading the list
        self.selectedPublisherId = 0
        self.selectedPublisherIndex = 0

        log.debug("End showPublisher")

    def showFilterControl(self, rows, controlId, showEntryAllItems):
        log.debug("begin showFilterControl: {0}".format(controlId))

        control = self.getControlById(controlId)
        if control is None:
            return

        control.setVisible(True)
        control.reset()  # Clear any existing entries in the ControlList

        items = []
        if showEntryAllItems:
            items.append(xbmcgui.ListItem(util.localize(32120), "0"))  # Add "All" entry

        for row in rows:
            items.append(xbmcgui.ListItem(helper.saveReadString(row[DataBaseObject.COL_NAME]), str(row[DataBaseObject.COL_ID])))

        control.addItems(items)

    def showCharacterFilter(self):
        log.debug("Begin showCharacterFilter")

        control = self.getControlById(CONTROL_CHARACTER)
        if control is None:
            return

        control.reset()

        showEntryAllItems = getSettings().getSetting(util.SETTING_RCB_SHOWENTRYALLCHARS).upper() == 'TRUE'

        items = []

        if showEntryAllItems:
            items.append(xbmcgui.ListItem(util.localize(32120), util.localize(32120)))
        items.append(xbmcgui.ListItem("0-9", "0-9"))

        for i in range(0, 26):
            char = chr(ord('A') + i)
            items.append(xbmcgui.ListItem(char, char))

        control.addItems(items)
        log.debug("End showCharacterFilter")

    def applyFilters(self):

        Logutil.log("Begin applyFilters", util.LOG_LEVEL_INFO)

        self.updateControls(False)
        xbmc.sleep(util.WAITTIME_UPDATECONTROLS)
        self.showGames()

    def _getMaxGamesToDisplay(self):
        # Set a limit of games to show
        maxNumGamesIndex = self.Settings.getSetting(util.SETTING_RCB_MAXNUMGAMESTODISPLAY)
        return util.MAXNUMGAMES_ENUM[int(maxNumGamesIndex)]

    # Functions for generating query strings for filtering

    def _buildLikeStatement(self, selectedCharacter, searchTerm):
        log.debug("buildLikeStatement")

        likeStatement = ''

        if selectedCharacter == util.localize(32120):  # All
            likeStatement = "0 = 0"
        elif selectedCharacter == '0-9':
            likeStatement = "(substr(name, 1, 1) IN ('0', '1', '2', '3', '4', '5', '6', '7', '8', '9'))"
        else:
            likeStatement = "name LIKE '{0}%'".format(selectedCharacter)

        if searchTerm != '':
            likeStatement += " AND name LIKE '%{0}%'".format(searchTerm)

        return likeStatement

    def _buildMissingFilterStatement(self, configobject):

        #32157 = ignore
        if configobject.showHideOption.lower() == util.localize(32157):
            return ''

        statement = ''

        andStatementInfo = self._buildInfoStatement(configobject.missingFilterInfo.andGroup, ' AND ')
        if andStatementInfo != '':
            statement = andStatementInfo

        orStatementInfo = self._buildInfoStatement(configobject.missingFilterInfo.orGroup, ' OR ')
        if orStatementInfo != '':
            if statement != '':
                statement = statement + ' OR '
            statement = statement + orStatementInfo

        andStatementArtwork = self._buildArtworkStatement(configobject, configobject.missingFilterArtwork.andGroup, ' AND ')
        if andStatementArtwork != '':
            if statement != '':
                statement = statement + ' OR '
            statement = statement + andStatementArtwork

        orStatementArtwork = self._buildArtworkStatement(configobject, configobject.missingFilterArtwork.orGroup, ' OR ')
        if orStatementArtwork != '':
            if statement != '':
                statement = statement + ' OR '
            statement = statement + orStatementArtwork

        if statement != '':
            statement = '(%s)' % (statement)
            #32161 = hide
            if configobject.showHideOption.lower() == util.localize(32161):
                statement = 'NOT ' + statement

        return statement

    def _buildInfoStatement(self, group, operator):
        statement = ''
        for item in group:
            if statement == '':
                statement = '('
            else:
                statement = statement + operator
            statement = statement + config.gameproperties[item][1]
        if statement != '':
            statement = statement + ')'

        return statement

    def _buildArtworkStatement(self, configobject, group, operator):
        statement = ''
        for item in group:
            if statement == '':
                statement = '('
            else:
                statement = statement + operator
            typeId = ''
            fileTypeRows = configobject.tree.findall('FileTypes/FileType')
            for element in fileTypeRows:
                if element.attrib.get('name') == item:
                    typeId = element.attrib.get('id')
                    break
            statement = statement + 'fileType%s IS NULL' % str(typeId)

        if statement != '':
            statement = statement + ')'
        return statement

    """
    def _checkMissingArtworkFilter(self, image_gamelist, image_clearlogo):

        #32157 = ignore
        if self.config.showHideOption.lower() == util.localize(32157):
            return True

        missinglist = []
        if not image_gamelist:
            missinglist.append('gamelist')
        if not image_clearlogo:
            missinglist.append('clearlogo')

        #check if one item from orGroup is missing
        resultOrGoup = True
        for item in self.config.missingFilterArtwork.orGroup:
            if item in missinglist:
                resultOrGoup = False
                break

        #check if all items from andGroup are missing
        #set True if no filter is configured
        resultAndGoup = len(self.config.missingFilterArtwork.andGroup) == 0
        for item in self.config.missingFilterArtwork.andGroup:
            if item not in missinglist:
                resultAndGoup = True
                break

        addItemToList = resultOrGoup and resultAndGoup

        #32159 = show
        #invert filter if we should show only games with missing artwork
        if self.config.showHideOption.lower() == util.localize(32159):
            addItemToList = not addItemToList

        return addItemToList
    """

    def _getGamesListQueryStatement(self):
        # Build statement for character search (where name LIKE 'A%')
        likeStatement = self._buildLikeStatement(self.selectedCharacter, self.searchTerm)

        # Build statement for missing filters
        missingFilterStatement = self._buildMissingFilterStatement(self.config)
        if missingFilterStatement != '':
            likeStatement = likeStatement + ' AND ' + missingFilterStatement

        return likeStatement

    # End of Functions for generating query strings for filtering

    def _isGameFavourite(self):
        try:
            if self.getControlById(CONTROL_BUTTON_FAVORITE).isSelected():
                return 1
        except AttributeError:
            pass

        return 0

    def showGames(self):
        Logutil.log("Begin showGames", util.LOG_LEVEL_INFO)

        self.lastPosition = -1

        preventUnfilteredSearch = self.Settings.getSetting(util.SETTING_RCB_PREVENTUNFILTEREDSEARCH).upper() == 'TRUE'
        if preventUnfilteredSearch:
            if self.selectedCharacter == util.localize(
                    32120) and self.selectedConsoleId == 0 and self.selectedGenreId == 0 and self.selectedYearId == 0 and self.selectedPublisherId == 0:
                Logutil.log("preventing unfiltered search", util.LOG_LEVEL_WARNING)
                return

        self.clearList()
        #32121 = Loading games...
        self.writeMsg(util.localize(32121))

        isFavorite = self._isGameFavourite()

        showFavoriteStars = self.Settings.getSetting(util.SETTING_RCB_SHOWFAVORITESTARS).upper() == 'TRUE'

        timestamp1 = time.clock()

        likeStatement = self._getGamesListQueryStatement()
        maxNumGames = self._getMaxGamesToDisplay()

        #games = GameView(self.gdb).getFilteredGames(self.selectedConsoleId, self.selectedGenreId, self.selectedYearId,
        #                                        self.selectedPublisherId, isFavorite, likeStatement, maxNumGames)
        games = GameView(self.gdb).getFilteredGames(self.selectedConsoleId, self.selectedGenreId, self.selectedYearId,
                                                self.selectedPublisherId, isFavorite, likeStatement, maxNumGames)

        timestamp2 = time.clock()
        diff = (timestamp2 - timestamp1) * 1000
        print "showGames: load %d games from db in %d ms" % (len(games), diff)

        #used to show percentage during game loading
        divisor = len(games) / 10
        counter = 0

        items = []
        for game in games:

            romcollection_id = str(game[GameView.COL_romCollectionId])

            try:
                romCollection = self.config.romCollections[romcollection_id]
            except KeyError:
                Logutil.log('Cannot get rom collection with id: ' + romcollection_id, util.LOG_LEVEL_ERROR)
                # Won't be able to get game images, move to next game
                continue

            item = xbmcgui.ListItem(game[GameView.COL_NAME], str(game[GameView.COL_ID]))
            item.setProperty('romCollectionId', romcollection_id)
            item.setProperty('romcollection', romCollection.name)
            item.setProperty('console', romCollection.name)
            item.setProperty('gameId', str(game[GameView.COL_ID]))
            item.setProperty('plot', game[GameView.COL_description])
            item.setProperty('playcount', str(game[GameView.COL_launchCount]))
            item.setProperty('originalTitle', game[GameView.COL_originalTitle])
            item.setProperty('alternateTitle', game[GameView.COL_alternateTitle])
            item.setProperty('developer', game[GameView.COL_developer])
            item.setProperty('publisher', game[GameView.COL_publisher])
            item.setProperty('year', game[GameView.COL_year])
            item.setProperty('genre', game[GameView.COL_genre])
            item.setProperty('gameCmd', game[GameView.COL_gameCmd])
            item.setProperty('alternateGameCmd', game[GameView.COL_alternateGameCmd])

            if game[GameView.COL_isFavorite] == 1 and showFavoriteStars:
                item.setProperty('isfavorite', '1')
            else:
                item.setProperty('isfavorite', '')

            #set gamelist artwork at startup
            item.setArt({
                        'icon': helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForGameList, game),
                        'thumb': helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForGameListSelected, game),
                        IMAGE_CONTROL_CLEARLOGO: helper.get_file_for_control_from_db(
                            [self.fileTypeClearlogo], game),
                        IMAGE_CONTROL_BACKGROUND: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewBackground, game),
                        IMAGE_CONTROL_GAMEINFO_BIG: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoBig, game),
                        IMAGE_CONTROL_GAMEINFO_UPPERLEFT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoUpperLeft, game),
                        IMAGE_CONTROL_GAMEINFO_UPPERRIGHT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoUpperRight, game),
                        IMAGE_CONTROL_GAMEINFO_LOWERLEFT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoLowerLeft, game),
                        IMAGE_CONTROL_GAMEINFO_LOWERRIGHT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoLowerRight, game),
                        IMAGE_CONTROL_GAMEINFO_UPPER: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoUpper, game),
                        IMAGE_CONTROL_GAMEINFO_LOWER: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoLower, game),
                        IMAGE_CONTROL_GAMEINFO_LEFT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoLeft, game),
                        IMAGE_CONTROL_GAMEINFO_RIGHT: helper.get_file_for_control_from_db(
                            romCollection.imagePlacingMain.fileTypesForMainViewGameInfoRight, game)
                         })

            if romCollection.autoplayVideoMain:
                self.loadVideoFiles(item, romCollection, game)

            # Add the listitem to the list
            items.append(item)

            #add progress to "loading games" message
            if len(games) > 1000:
                if counter >= divisor and counter % divisor == 0:
                    percent = (len(games) / divisor) * (counter / divisor)
                    #32121 = Loading games...
                    self.writeMsg('%s (%i%%)' % (util.localize(32121), percent))
                counter = counter + 1

        #add dummy item to keep the list navigable
        if len(items) == 0:
            #32412 = No Games found
            item = xbmcgui.ListItem(util.localize(32412), '')
            items.append(item)

        #Add list to window
        self.addItems(items)

        self.writeMsg("")

        timestamp3 = time.clock()
        diff = (timestamp3 - timestamp2) * 1000
        Logutil.log("showGames: load %i games to list in %d ms" % (self.getListSize(), diff), util.LOG_LEVEL_INFO)

        Logutil.log("End showGames", util.LOG_LEVEL_INFO)

    def showGameInfo(self):
        """ Called when a game is selected in the list; retrieves the object and sets the artwork data. This is to
            work around the fact that we may delay loading it in the main list population as a caching mechanism
        """

        #current implementation does not need showGameInfo as all data is loaded in showGames.
        pass

        """
        Logutil.log("Begin showGameInfo", util.LOG_LEVEL_INFO)
        starttime = time.clock()
        self.writeMsg("")

        selectedGame = self.getSelectedItem()

        if selectedGame is None:
            Logutil.log("selectedGame == None in showGameInfo", util.LOG_LEVEL_WARNING)
            return

        Logutil.log(
            'Selected game with property gameId {0}, romCollectionId {1}'.format(selectedGame.getProperty('gameId'),
                                                                                 selectedGame.getProperty(
                                                                                     'romCollectionId')),
            util.LOG_LEVEL_DEBUG)

        try:
            romCollection = self.config.romCollections[selectedGame.getProperty('romCollectionId')]
        except Exception as err:
            print err.message
            Logutil.log('Cannot get rom collection with id: ' + str(selectedGame.getProperty('romCollectionId')),
                        util.LOG_LEVEL_ERROR)
            return

        if romCollection.autoplayVideoMain:
            self.loadVideoFiles(selectedGame, romCollection, selectedGame)

        endtime = time.clock()
        diff = (endtime - starttime) * 1000
        Logutil.log('Time taken to showGameInfo using new format: {0}ms'.format(diff), util.LOG_LEVEL_INFO)

        Logutil.log("End showGameInfo", util.LOG_LEVEL_INFO)
        """

    def getSelectedItem(self):
        if self.getListSize() == 0:
            Logutil.log("ListSize == 0 in getSelectedItem", util.LOG_LEVEL_WARNING)
            return

        pos = self.getCurrentListPosition()
        if pos == -1:
            pos = 0

        return self.getListItem(pos)

    def launchEmu(self):

        Logutil.log("Begin launchEmu", util.LOG_LEVEL_INFO)

        if self.getListSize() == 0:
            Logutil.log("ListSize == 0 in launchEmu", util.LOG_LEVEL_WARNING)
            return

        pos = self.getCurrentListPosition()
        if pos == -1:
            pos = 0
        selectedGame = self.getListItem(pos)

        if selectedGame == None:
            Logutil.log("selectedGame == None in launchEmu", util.LOG_LEVEL_WARNING)
            return

        gameId = selectedGame.getProperty('gameId')
        Logutil.log("launching game with id: " + str(gameId), util.LOG_LEVEL_INFO)

        #stop video (if playing)
        if self.player.isPlayingVideo():
            #self.player.stoppedByRCB = True
            self.player.stop()

        from launcher import RCBLauncher
        launcher = RCBLauncher()
        launcher.launchEmu(self.gdb, self, gameId, self.config, selectedGame)
        Logutil.log("End launchEmu", util.LOG_LEVEL_INFO)

    def updateDB(self):
        Logutil.log("Begin updateDB", util.LOG_LEVEL_INFO)
        self.importGames(None, False)
        Logutil.log("End updateDB", util.LOG_LEVEL_INFO)

    def rescrapeGames(self, romCollections):
        Logutil.log("Begin rescrapeGames", util.LOG_LEVEL_INFO)
        self.importGames(romCollections, True)
        self.config.readXml()
        Logutil.log("End rescrapeGames", util.LOG_LEVEL_INFO)

    def importGames(self, romCollections, isRescrape):
        self.saveViewState(False)
        self.clearList()
        self.checkImport(3, romCollections, isRescrape)
        self.updateControls(True)
        self.loadViewState()

    def updateGamelist(self):
        #only update controls if they are available
        if self.initialized:
            self.showGames()
            focusControl = self.getControlById(CONTROL_GAMES_GROUP_START)
            if focusControl != None:
                self.setFocus(focusControl)
            xbmc.sleep(util.WAITTIME_UPDATECONTROLS)
            self.showGameInfo()

    def deleteGame(self, gameID):
        Logutil.log("Begin deleteGame", util.LOG_LEVEL_INFO)

        Logutil.log("Delete Year", util.LOG_LEVEL_INFO)
        Year(self.gdb).delete(gameID)
        Logutil.log("Delete Publisher", util.LOG_LEVEL_INFO)
        Publisher(self.gdb).delete(gameID)
        Logutil.log("Delete Developer", util.LOG_LEVEL_INFO)
        Developer(self.gdb).delete(gameID)
        Logutil.log("Delete Genre", util.LOG_LEVEL_INFO)
        Genre(self.gdb).delete(gameID)
        Logutil.log("Delete File", util.LOG_LEVEL_INFO)
        File(self.gdb).delete(gameID)
        Logutil.log("Delete Game", util.LOG_LEVEL_INFO)
        Game(self.gdb).delete(gameID)

        Logutil.log("End deleteGame", util.LOG_LEVEL_INFO)

    def deleteRCGames(self, rcID, rcDelete, rDelete):
        Logutil.log("begin Delete Games", util.LOG_LEVEL_INFO)
        count = 0

        rcList = GameView(self.gdb).getFilteredGames(rcID, 0, 0, 0, 0, '0 = 0')
        progressDialog = dialogprogress.ProgressDialogGUI()
        progressDialog.itemCount = len(rcList)

        if rcList != None:
            progDialogRCDelStat = util.localize(32104) + " (%i / %i)" % (count, progressDialog.itemCount)
            progressDialog.writeMsg(util.localize(32105), progDialogRCDelStat, "", count)
            for items in rcList:
                count = count + 1
                progDialogRCDelStat = util.localize(32104) + " (%i / %i)" % (count, progressDialog.itemCount)
                progressDialog.writeMsg("", progDialogRCDelStat, "", count)
                self.deleteGame(items[Game.COL_ID])
            if len(rcList) > 0:
                progressDialog.writeMsg("", util.localize(32106), "", count)
            else:
                progressDialog.writeMsg(util.localize(32106), "", "", count)
            time.sleep(1)
            self.gdb.commit()
            self.config = Config(None)
            self.config.readXml()
            self.clearList()
            xbmc.sleep(util.WAITTIME_UPDATECONTROLS)
            self.updateControls(True)
            if rDelete:
                self.selectedConsoleId = int(self.setFilterSelection(CONTROL_CONSOLES, self.selectedConsoleIndex))
                self.setFilterSelection(CONTROL_GAMES_GROUP_START, 0)
            self.showGames()

        rcList = None
        Logutil.log("end Delete Games", util.LOG_LEVEL_INFO)

    def cleanDB(self):
        Logutil.log("Begin cleanDB", util.LOG_LEVEL_INFO)

        count = 0
        removeCount = 0
        filelist = File(self.gdb).getFilesList()
        progressDialog2 = dialogprogress.ProgressDialogGUI()
        progressDialog2.itemCount = len(filelist)
        progDialogCleanStat = util.localize(32107) + " (%i / %i)" % (count, progressDialog2.itemCount)
        progressDialog2.writeMsg(util.localize(32108), progDialogCleanStat, "")
        if filelist != None:
            for items in filelist:
                count = count + 1
                progDialogCleanStat = util.localize(32107) + " (%i / %i)" % (count, progressDialog2.itemCount)
                progressDialog2.writeMsg("", progDialogCleanStat, "", count)
                if os.path.exists(items[File.COL_NAME]) != True:
                    if items[File.COL_fileTypeId] == 0:
                        self.deleteGame(items[File.COL_parentId])
                    else:
                        File(self.gdb).deleteByFileId(items[File.COL_ID])
                    removeCount = removeCount + 1
            progressDialog2.writeMsg("", util.localize(32109), "", count)
            self.gdb.compact()
            time.sleep(.5)
            progressDialog2.writeMsg("", util.localize(32110), "", count)
            time.sleep(1)
            self.showGames()
        Logutil.log("End cleanDB", util.LOG_LEVEL_INFO)

    def showGameInfoDialog(self):
        """ Called when a game is opened in the GameInfo dialog """
        Logutil.log("Begin showGameInfoDialog", util.LOG_LEVEL_INFO)

        if self.getListSize() == 0:
            Logutil.log("ListSize == 0 in saveViewState", util.LOG_LEVEL_WARNING)
            return

        selectedGameIndex = self.getCurrentListPosition()
        if selectedGameIndex == -1:
            selectedGameIndex = 0
        selectedGame = self.getListItem(selectedGameIndex)
        if selectedGame == None:
            Logutil.log("selectedGame == None in showGameInfoDialog", util.LOG_LEVEL_WARNING)
            return

        gameId = selectedGame.getProperty('gameId')

        self.saveViewMode()

        if self.player.isPlayingVideo():
            self.player.stop()

        self.gameinfoDialogOpen = True

        constructorParam = "720p"

        import dialoggameinfo
        try:
            gid = dialoggameinfo.UIGameInfoView("script-RCB-gameinfo.xml", util.getAddonInstallPath(),
                                                util.getConfiguredSkin(), constructorParam, gdb=self.gdb, gameId=gameId,
                                                listItem=selectedGame,
                                                consoleId=self.selectedConsoleId, genreId=self.selectedGenreId,
                                                yearId=self.selectedYearId, publisherId=self.selectedPublisherId,
                                                selectedGameIndex=selectedGameIndex,
                                                consoleIndex=self.selectedConsoleIndex,
                                                genreIndex=self.selectedGenreIndex, yearIndex=self.selectedYearIndex,
                                                publisherIndex=self.selectedPublisherIndex,
                                                selectedCharacter=self.selectedCharacter,
                                                selectedCharacterIndex=self.selectedCharacterIndex,
                                                controlIdMainView=self.selectedControlId, config=self.config,
                                                settings=self.Settings,
                                                fileTypeGameplay=self.fileTypeGameplay)
        except:
            gid = dialoggameinfo.UIGameInfoView("script-RCB-gameinfo.xml", util.getAddonInstallPath(), "Default",
                                                constructorParam, gdb=self.gdb, gameId=gameId, listItem=selectedGame,
                                                consoleId=self.selectedConsoleId, genreId=self.selectedGenreId,
                                                yearId=self.selectedYearId, publisherId=self.selectedPublisherId,
                                                selectedGameIndex=selectedGameIndex,
                                                consoleIndex=self.selectedConsoleIndex,
                                                genreIndex=self.selectedGenreIndex, yearIndex=self.selectedYearIndex,
                                                publisherIndex=self.selectedPublisherIndex,
                                                selectedCharacter=self.selectedCharacter,
                                                selectedCharacterIndex=self.selectedCharacterIndex,
                                                controlIdMainView=self.selectedControlId, config=self.config,
                                                settings=self.Settings,
                                                fileTypeGameplay=self.fileTypeGameplay)

        del gid

        self.gameinfoDialogOpen = False

        #force restart of video if available
        #selectedGame.setProperty('gameplaymain', video)
        self.setFocus(self.getControl(CONTROL_GAMES_GROUP_START))

        Logutil.log("End showGameInfoDialog", util.LOG_LEVEL_INFO)

    def showContextMenu(self):

        import dialogcontextmenu

        constructorParam = "720p"
        try:
            cm = dialogcontextmenu.ContextMenuDialog("script-RCB-contextmenu.xml", util.getAddonInstallPath(),
                                                     util.getConfiguredSkin(), constructorParam, gui=self)
        except:
            cm = dialogcontextmenu.ContextMenuDialog("script-RCB-contextmenu.xml", util.getAddonInstallPath(),
                                                     "Default", constructorParam, gui=self)

        del cm

    def loadVideoFiles(self, listItem, romCollection, game):

        #check if we should use autoplay video
        if romCollection.autoplayVideoMain:
            listItem.setProperty('autoplayvideomain', 'true')
        else:
            listItem.setProperty('autoplayvideomain', '')

        #get video window size
        if romCollection.imagePlacingMain.name.startswith('gameinfosmall'):
            listItem.setProperty('videosizesmall', 'small')
            listItem.setProperty('videosizebig', '')
        else:
            listItem.setProperty('videosizebig', 'big')
            listItem.setProperty('videosizesmall', '')

        if self.fileTypeGameplay == None:
            Logutil.log("fileType gameplay == None. No video loaded.", util.LOG_LEVEL_INFO)

        #load gameplay videos
        video = helper.get_file_for_control_from_db((self.fileTypeGameplay,), game)
        if video:
            listItem.setProperty('gameplaymain', video)

        if video == "" or video is None or not romCollection.autoplayVideoMain:
            if self.player.isPlayingVideo():
                self.player.stop()

    def checkImport(self, doImport, romCollections, isRescrape):

        #doImport: 0=nothing, 1=import Settings and Games, 2=import Settings only, 3=import games only
        if doImport == 0:
            return

        #Show options dialog if user wants to see it
        #Import is started from dialog
        showImportOptionsDialog = self.Settings.getSetting(util.SETTING_RCB_SHOWIMPORTOPTIONSDIALOG).upper() == 'TRUE'
        if showImportOptionsDialog:
            import dialogimportoptions
            constructorParam = "720p"
            try:
                iod = dialogimportoptions.ImportOptionsDialog("script-RCB-importoptions.xml",
                                                              util.getAddonInstallPath(),
                                                              util.getConfiguredSkin(),
                                                              constructorParam, gui=self,
                                                              romCollections=romCollections,
                                                              isRescrape=isRescrape)
            except:
                iod = dialogimportoptions.ImportOptionsDialog("script-RCB-importoptions.xml",
                                                              util.getAddonInstallPath(),
                                                              "Default",
                                                              constructorParam, gui=self,
                                                              romCollections=romCollections,
                                                              isRescrape=isRescrape)
            del iod
        else:
            #32118 = Do you want to import Games now?
            message = util.localize(32118)

            dialog = xbmcgui.Dialog()

            #32500 = Import Games
            retGames = dialog.yesno(util.localize(32999), util.localize(32500), message)
            if retGames == True:
                #Import Games
                if romCollections == None:
                    self.doImport(self.config.romCollections, isRescrape, False)
                else:
                    self.doImport(romCollections, isRescrape, False)

    def doImport(self, romCollections, isRescrape, scrapeInBackground, selectedRomCollection=None,
                 selectedScraper=None):

        if scrapeInBackground:
            path = os.path.join(self.Settings.getAddonInfo('path'), 'dbUpLauncher.py')
            log.info('Launch external update script: %s' % path)
            xbmc.executebuiltin("RunScript(%s, selectedRomCollection=%s, selectedScraper=%s)"
                                % (path, selectedRomCollection, selectedScraper))
            #exit RCB
            self.quit = True
            self.exit()
        else:
            import dbupdate

            progressDialog = dialogprogress.ProgressDialogGUI()
            progressDialog.writeMsg(util.localize(32111), "", "")

            updater = dbupdate.DBUpdate()
            updater.updateDB(self.gdb, progressDialog, romCollections, isRescrape)
            del updater
            progressDialog.writeMsg("", "", "", -1)
            del progressDialog

    def checkUpdateInProgress(self):

        Logutil.log("checkUpdateInProgress", util.LOG_LEVEL_INFO)

        scrapeOnStartupAction = self.Settings.getSetting(util.SETTING_RCB_SCRAPEONSTARTUPACTION)
        Logutil.log("scrapeOnStartupAction = " + str(scrapeOnStartupAction), util.LOG_LEVEL_INFO)

        if scrapeOnStartupAction == 'update':
            retCancel = xbmcgui.Dialog().yesno(util.localize(32999), util.localize(32112), util.localize(32113))
            if retCancel == True:
                self.Settings.setSetting(util.SETTING_RCB_SCRAPEONSTARTUPACTION, 'cancel')
            return True

        elif scrapeOnStartupAction == 'cancel':
            retForceCancel = xbmcgui.Dialog().yesno(util.localize(32999), util.localize(32114), util.localize(32205))

            #HACK: Assume that there is a problem with canceling the action
            if retForceCancel == True:
                self.Settings.setSetting(util.SETTING_RCB_SCRAPEONSTARTUPACTION, 'nothing')

            return True

        return False

    def saveViewState(self, isOnExit):

        Logutil.log("Begin saveViewState", util.LOG_LEVEL_INFO)

        if self.getListSize() == 0:
            Logutil.log("ListSize == 0 in saveViewState", util.LOG_LEVEL_WARNING)
            return

        selectedGameIndex = self.getCurrentListPosition()
        if selectedGameIndex == -1:
            selectedGameIndex = 0
        if selectedGameIndex == None:
            Logutil.log("selectedGameIndex == None in saveViewState", util.LOG_LEVEL_WARNING)
            return

        self.saveViewMode()

        helper.saveViewState(self.gdb, isOnExit, util.VIEW_MAINVIEW, selectedGameIndex, self.selectedConsoleId,
                             self.selectedGenreId, self.selectedPublisherId,
                             self.selectedYearId, self.selectedCharacter, self.selectedControlId, None,
                             self.Settings)

        Logutil.log("End saveViewState", util.LOG_LEVEL_INFO)

    def saveViewMode(self):

        Logutil.log("Begin saveViewMode", util.LOG_LEVEL_INFO)

        view_mode = ""
        for control_id in range(CONTROL_GAMES_GROUP_START, CONTROL_GAMES_GROUP_END + 1):
            try:
                if xbmc.getCondVisibility("Control.IsVisible(%i)" % control_id):
                    view_mode = repr(control_id)
                    break
            except:
                pass

        self.Settings.setSetting(util.SETTING_RCB_VIEW_MODE, view_mode)

        #favorites
        controlFavorites = self.getControlById(CONTROL_BUTTON_FAVORITE)
        if controlFavorites != None:
            self.Settings.setSetting(util.SETTING_RCB_FAVORITESSELECTED, str(controlFavorites.isSelected()))

        #searchText
        controlSearchText = self.getControlById(CONTROL_BUTTON_SEARCH)
        if controlSearchText != None:
            self.Settings.setSetting(util.SETTING_RCB_SEARCHTEXT, self.searchTerm)

        Logutil.log("End saveViewMode", util.LOG_LEVEL_INFO)

    def loadViewState(self):

        Logutil.log("Begin loadViewState", util.LOG_LEVEL_INFO)

        rcbSetting = helper.getRCBSetting(self.gdb)
        if rcbSetting == None:
            Logutil.log("rcbSetting == None in loadViewState", util.LOG_LEVEL_WARNING)
            return

        rcid = rcbSetting[RCBSetting.COL_lastSelectedConsoleIndex]
        button = self.getControlById(CONTROL_CONSOLES)
        if rcid > 0:
            romcollection = self.config.getRomCollectionById(str(rcid))
            button.setLabel(romcollection.name)
            self.selectedConsoleId = int(romcollection.id)
        else:
            button.setLabel(util.localize(32120))

        genreid = rcbSetting[RCBSetting.COL_lastSelectedGenreIndex]
        button = self.getControlById(CONTROL_GENRE)
        if genreid > 0:
            genre = Genre(self.gdb).getObjectById(genreid)
            button.setLabel(genre[Genre.COL_NAME])
            self.selectedGenreId = genre[Genre.COL_ID]
        else:
            button.setLabel(util.localize(32120))

        yearid = rcbSetting[RCBSetting.COL_lastSelectedYearIndex]
        button = self.getControlById(CONTROL_YEAR)
        if yearid > 0:
            year = Year(self.gdb).getObjectById(yearid)
            button.setLabel(year[Year.COL_NAME])
            self.selectedYearId = year[Year.COL_ID]
        else:
            button.setLabel(util.localize(32120))

        publisherid = rcbSetting[RCBSetting.COL_lastSelectedPublisherIndex]
        button = self.getControlById(CONTROL_PUBLISHER)
        if publisherid > 0:
            publisher = Publisher(self.gdb).getObjectById(publisherid)
            button.setLabel(publisher[Publisher.COL_NAME])
            self.selectedPublisherId = publisher[Publisher.COL_ID]
        else:
            button.setLabel(util.localize(32120))

        character = rcbSetting[RCBSetting.COL_lastSelectedCharacterIndex]
        button = self.getControlById(CONTROL_CHARACTER)
        if character != util.localize(32120):
            button.setLabel(character)
            self.selectedCharacter = character
        else:
            button.setLabel(util.localize(32120))


        """
        #first load console filter
        self.showConsoles()

        #set console filter selection
        if rcbSetting[RCBSetting.COL_lastSelectedConsoleIndex] != None:
            self.selectedConsoleId = int(
                self.setFilterSelection(CONTROL_CONSOLES, rcbSetting[RCBSetting.COL_lastSelectedConsoleIndex]))
            self.selectedConsoleIndex = rcbSetting[RCBSetting.COL_lastSelectedConsoleIndex]

        #load other filters
        self.showGenre()
        if rcbSetting[RCBSetting.COL_lastSelectedGenreIndex] != None:
            self.selectedGenreId = int(
                self.setFilterSelection(CONTROL_GENRE, rcbSetting[RCBSetting.COL_lastSelectedGenreIndex]))
            self.selectedGenreIndex = rcbSetting[RCBSetting.COL_lastSelectedGenreIndex]

        self.showYear()
        if rcbSetting[RCBSetting.COL_lastSelectedYearIndex] != None:
            self.selectedYearId = int(
                self.setFilterSelection(CONTROL_YEAR, rcbSetting[RCBSetting.COL_lastSelectedYearIndex]))
            self.selectedYearIndex = rcbSetting[RCBSetting.COL_lastSelectedYearIndex]

        self.showPublisher()
        if rcbSetting[RCBSetting.COL_lastSelectedPublisherIndex] != None:
            self.selectedPublisherId = int(
                self.setFilterSelection(CONTROL_PUBLISHER, rcbSetting[RCBSetting.COL_lastSelectedPublisherIndex]))
            self.selectedPublisherIndex = rcbSetting[RCBSetting.COL_lastSelectedPublisherIndex]

        self.showCharacterFilter()
        if rcbSetting[RCBSetting.COL_lastSelectedCharacterIndex] != None:
            self.selectedCharacter = self.setFilterSelection(CONTROL_CHARACTER,
                                                             rcbSetting[RCBSetting.COL_lastSelectedCharacterIndex])
            self.selectedCharacterIndex = rcbSetting[RCBSetting.COL_lastSelectedCharacterIndex]
        """

        #reset view mode
        viewModeId = self.Settings.getSetting(util.SETTING_RCB_VIEW_MODE)
        if viewModeId != None and viewModeId != '':
            xbmc.executebuiltin("Container.SetViewMode(%i)" % int(viewModeId))

        #searchText
        self.searchTerm = self.Settings.getSetting(util.SETTING_RCB_SEARCHTEXT)
        searchButton = self.getControlById(CONTROL_BUTTON_SEARCH)
        if self.searchTerm != '' and searchButton != None:
            searchButton.setLabel(util.localize(32117) + ': ' + self.searchTerm)

        #favorites
        isFavoriteButton = self.getControlById(CONTROL_BUTTON_FAVORITE)
        if isFavoriteButton != None:
            favoritesSelected = self.Settings.getSetting(util.SETTING_RCB_FAVORITESSELECTED)
            isFavoriteButton.setSelected(favoritesSelected == '1')

        # Reset game list
        self.showGames()

        #self.setFilterSelection(CONTROL_GAMES_GROUP_START, rcbSetting[RCBSetting.COL_lastSelectedGameIndex])

        #always set focus on game list on start
        focusControl = self.getControlById(CONTROL_GAMES_GROUP_START)
        if focusControl != None:
            self.setFocus(focusControl)

        self.showGameInfo()

        Logutil.log("End loadViewState", util.LOG_LEVEL_INFO)

    def setFilterSelection(self, controlId, selectedIndex):

        Logutil.log("Begin setFilterSelection", util.LOG_LEVEL_DEBUG)

        if selectedIndex != None:
            control = self.getControlById(controlId)
            if control == None:
                Logutil.log("control == None in setFilterSelection", util.LOG_LEVEL_WARNING)
                return 0

            if controlId == CONTROL_GAMES_GROUP_START:
                listSize = self.getListSize()
                if listSize == 0 or selectedIndex > listSize - 1:
                    Logutil.log("ListSize == 0 or index out of range in setFilterSelection", util.LOG_LEVEL_WARNING)
                    return 0

                self.setCurrentListPosition(selectedIndex)
                #HACK: selectItem takes some time and we can't read selectedItem immediately
                xbmc.sleep(util.WAITTIME_UPDATECONTROLS)
                selectedItem = self.getListItem(selectedIndex)

            else:
                if selectedIndex > control.size() - 1:
                    Logutil.log("Index out of range in setFilterSelection", util.LOG_LEVEL_WARNING)
                    return 0

                control.selectItem(selectedIndex)
                #HACK: selectItem takes some time and we can't read selectedItem immediately
                xbmc.sleep(util.WAITTIME_UPDATECONTROLS)
                selectedItem = control.getSelectedItem()

            if selectedItem == None:
                Logutil.log("End setFilterSelection", util.LOG_LEVEL_DEBUG)
                return 0
            label2 = selectedItem.getLabel2()
            Logutil.log("End setFilterSelection", util.LOG_LEVEL_DEBUG)
            return label2
        else:
            Logutil.log("End setFilterSelection", util.LOG_LEVEL_DEBUG)
            return 0

    def getControlById(self, controlId):
        try:
            control = self.getControl(controlId)
        except Exception, (exc):
            #HACK there seems to be a problem with recognizing the scrollbar controls
            if controlId not in (CONTROL_SCROLLBARS):
                Logutil.log("Control with id: %s could not be found. Check WindowXML file. Error: %s" % (
                str(controlId), str(exc)), util.LOG_LEVEL_ERROR)
                self.writeMsg(util.localize(32025) % str(controlId))
            return None

        return control

    def writeMsg(self, msg, count=0):

        control = self.getControlById(CONTROL_LABEL_MSG)
        if control == None:
            Logutil.log("RCB_WARNING: control == None in writeMsg", util.LOG_LEVEL_WARNING)
            return
        try:
            control.setLabel(msg)
        except:
            pass

    def exit(self):

        Logutil.log("exit", util.LOG_LEVEL_INFO)

        self.saveViewState(True)

        self.gdb.close()
        self.close()


def main():
    skin = util.getConfiguredSkin()

    kodiVersion = KodiVersions.getKodiVersion()
    Logutil.log("Kodi Version = " + str(kodiVersion), util.LOG_LEVEL_INFO)

    if KodiVersions.getKodiVersion() > KodiVersions.KRYPTON:
        ui = UIGameDB("script-Rom_Collection_Browser-main.xml", util.getAddonInstallPath(), skin, "720p", True)
    else:
        ui = UIGameDB("script-Rom_Collection_Browser-main.xml", util.getAddonInstallPath(), skin, "720p")

    ui.doModal()
    del ui


main()
