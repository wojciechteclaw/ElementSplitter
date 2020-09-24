import clr
clr.AddReference('ProtoGeometry')
from Autodesk.DesignScript.Geometry import *
from sys import path as sysPath
sysPath.append("C:\Program Files (x86)\IronPython 2.7\Lib")
import math

# Import DocumentManager and TransactionManager
clr.AddReference("RevitServices")
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

# Import RevitAPI
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as db
clr.AddReference("RevitNodes")
doc = DocumentManager.Instance.CurrentDBDocument


# functions collecting side elements
def getListOfLevelIds(doc):
    fltr = db.ElementCategoryFilter(db.BuiltInCategory.OST_Levels)
    if (IN[1]):
        allLevels = db.FilteredElementCollector(doc).WherePasses(fltr).WhereElementIsNotElementType().ToElements()
    else:
        allLevels = db.FilteredElementCollector(doc, doc.ActiveView.Id).WherePasses(fltr).WhereElementIsNotElementType().ToElements()
    lst = list()
    for level in sorted(allLevels, key=lambda x: x.Elevation):
        lst.append(level.Id)
    return lst


class WallOpenings():

    def __init__(self, levelsList, wall, doc):
        self. levels = levelsList
        self.wall = wall
        self.doc = doc
        self.getListOfOpeningsHostedInWall()
        self.createDictionaryOpeningAndItsLevel()

    def deleteOpeningsNotInWallRange(self):
        wallBaseConstrain = self.wall.get_Parameter(db.BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()
        for openingId in self.openingDictionary:
            openingRecalculatedLevel = self.openingDictionary[openingId]
            if openingRecalculatedLevel != wallBaseConstrain:
                TransactionManager.Instance.EnsureInTransaction(self.doc)
                self.doc.Delete(openingId)
                TransactionManager.Instance.TransactionTaskDone()
           

    def getListOfOpeningsHostedInWall(self):
        self.allOpeningsId = self.wall.GetDependentElements(db.ElementCategoryFilter(db.BuiltInCategory.OST_GenericModel))
        
    def createDictionaryOpeningAndItsLevel(self):
        self.openingDictionary = {}
        for openingId in self.allOpeningsId:
            opening = doc.GetElement(openingId)
            self.openingDictionary[openingId] = self.getClosestLevelId(opening)
        return self.openingDictionary

    def getClosestLevelId(self, opening):
        openingLevelId = opening.LookupParameter("Level").AsElementId()
        index = self.levels.index(openingLevelId)
        openingGeneralElevation = doc.GetElement(levels[index]).Elevation + opening.LookupParameter("Elevation").AsDouble()
        if index != len(self.levels) - 1:
            newIndexOfLevel = self.getLevelIndex(index, opening, openingGeneralElevation)
            return self.levels[newIndexOfLevel]
        else:
            return levels[index]

    def getLevelIndex(self, index, opening, openingGeneralElevation):
        i = index
        while i < len(self.levels):
            levelElement = doc.GetElement(self.levels[i])
            if levelElement.Elevation <= openingGeneralElevation:
                index = i
            else:
                break
            i += 1
        return index


# splitter main class - abstract class
class ElementSplitter():

    def __init__(self, doc, element, levelsList):
        self.doc = doc
        self.element = element
        self.levelsList = levelsList
    
    # Lanuch function which tries to modify offsets
    def modifyLevelsAndOffsets(self):
        self.tryToModifyBaseBoundries()
        self.tryToModifyTopBoundries()
    
    # Gets data from splitting element
    def getElementData(self):
        self.param_Mark = self.element.LookupParameter("Mark").AsString()
    
    # Sets basic parameters to newly created elements
    def setElementData(self, element):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        try:
            element.LookupParameter("Mark").Set(self.param_Mark)
        except:
            pass

        TransactionManager.Instance.TransactionTaskDone()
    
    # Copies element
    def copyElement(self):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        element = db.ElementTransformUtils.CopyElement(self.doc, self.element.Id, db.XYZ(0,0,0))
        TransactionManager.Instance.TransactionTaskDone()
        return element

    # Deletes element
    def deleteOriginalElement(self):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        self.doc.Delete(self.element.Id)
        TransactionManager.Instance.TransactionTaskDone()

    # Additional element for columns with top offset
    def additionalElementWhileTopOffset(self, index):
        if self.getTopOffsetValue() != 0:
            element = self.doc.GetElement(self.copyElement()[0])
            self.setBaseOffsetValue(element, 0)
            self.setTopOffsetValue(element, self.getTopOffsetValue())
            self.setBaseConstraintLevelId(element, self.levelsList[index + 1])
            self.setTopConstraintLevelId(element, self.levelsList[index + 1])
            self.additionalModificationOfElement(element)
            return element

    # General function for splitting elements
    def splitElement(self):
        self.getElementData()
        if self.isElementPossibleToSplit():
            self.listOfElementsToJoin = list()
            startLevelIndex = self.getIndexOfBaseLevel()
            endLevelIndex = self.getIndexOfTopLevel()
            for i in range(startLevelIndex, endLevelIndex):
                elementToChange = self.doc.GetElement(self.copyElement()[0])
                self.listOfElementsToJoin.append(elementToChange)
                if i == startLevelIndex:
                    self.setBaseOffsetValue(elementToChange, self.getBaseOffsetValue())
                    self.setTopOffsetValue(elementToChange, 0)
                elif i == endLevelIndex - 1:
                    self.setBaseOffsetValue(elementToChange, 0)
                    # optionaly two lines below might be replaced with:
                    # self.setTopOffsetValue(elementToChange, self.getTopOffsetValue())
                    self.setTopOffsetValue(elementToChange, 0)
                    additionalElement = self.additionalElementWhileTopOffset(i)
                    self.listOfElementsToJoin.append(additionalElement)
                else:
                    self.setBaseOffsetValue(elementToChange, 0)
                    self.setTopOffsetValue(elementToChange, 0)
                    self.setElementData(elementToChange)
                self.setBaseConstraintLevelId(elementToChange, self.levelsList[i])
                self.setTopConstraintLevelId(elementToChange, self.levelsList[i+1])
                self.additionalModificationOfElement(elementToChange)
            self.joinElementsInList()
            self.deleteOriginalElement()
    
    # Joins list of elements 
    def joinElementsInList(self):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        for i in range(len(self.listOfElementsToJoin)-1):
            try:
                db.JoinGeometryUtils.JoinGeometry(self.doc, self.listOfElementsToJoin[i], self.listOfElementsToJoin[i + 1])
            except:
                pass
        TransactionManager.Instance.TransactionTaskDone()


    # Adds Additional modification to element or its subelements
    def additionalModificationOfElement(self, elementToChange):
        pass

    # checks if element goes trought more than
    def isElementPossibleToSplit(self):
        self.modifyLevelsAndOffsets()
        startLevelIndex = self.getIndexOfBaseLevel()
        endLevelIndex = self.getIndexOfTopLevel()
        if startLevelIndex + 1 == endLevelIndex:
            return False
        else:
            return True
        
    # Calculates distance between levels
    def getDistanceBetweenLevels(self, originalLevelIndex, newLevelIndex):
        listOfLevels = self.convertListOfLevelIdsToElements()
        return math.fabs(listOfLevels[originalLevelIndex].Elevation - listOfLevels[newLevelIndex].Elevation)

    # Converts list of levels ids to elements
    def convertListOfLevelIdsToElements(self):
        lst = list()
        for levelId in self.levelsList:
            lst.append(self.doc.GetElement(levelId))
        return lst

    # tries to modify element to set level as high as it is possible
    # and reduce offset. Instead of situation: Level no 3 with offset 10m
    # it changes elements base level ie. Level no 5 with offset -50cm 
    def tryToModifyTopBoundries(self):
        try:
            index = self.getIndexOfTopLevel()
            endLevelOffset = self.getTopOffsetValue()
        # means it's unconnected wall so treat base constraint as top with 
        # offset as unconnected height +/- base offset value
        except ValueError:
            index = self.getIndexOfBaseLevel()
            if self.getBaseOffsetValue() < 0:
                endLevelOffset = self.getHeight() + self.getBaseOffsetValue()
            else:
                endLevelOffset = self.getHeight() - self.getBaseOffsetValue()
        levels = self.convertListOfLevelIdsToElements()
        indexOfNewLevel = None
        if index != len(levels) - 1:
            for i in range(index + 1, len(levels)):
                if endLevelOffset >= (levels[i].Elevation - levels[index].Elevation):
                    indexOfNewLevel = i
                else:
                    break
        if indexOfNewLevel != None:
            self.setNewTopBoundries(index, indexOfNewLevel)

    # Sets new top boundry for element
    def setNewTopBoundries(self, levelIndex, newLevelIndex):
        differenceInOffset = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
        if  self.getTopConstraintLevelId().IntegerValue == -1: 
            if self.getBaseOffsetValue() < 0:
                newOffset = self.getHeight() - differenceInOffset + self.getBaseOffsetValue()
            else:
                newOffset = self.getHeight() - differenceInOffset - self.getBaseOffsetValue()
        else:
            newOffset = self.getTopOffsetValue() - differenceInOffset
        newLevelId = self.levelsList[newLevelIndex]
        TransactionManager.Instance.EnsureInTransaction(doc)
        self.setTopConstraintLevelId(self.element, newLevelId)
        self.setTopOffsetValue(self.element, newOffset)
        TransactionManager.Instance.TransactionTaskDone()

    # tries to modify element to set level as low as it is possible
    # and reduce offset. Instead of situation: Level no 3 with offset -10m
    # it changes elements base level ie. Level no 0 with offset -50cm 
    def tryToModifyBaseBoundries(self):
        index = self.getIndexOfBaseLevel()
        startLevelId = self.getBaseConstraintLevelId()
        startLevelOffset = self.getBaseOffsetValue()
        levels = self.convertListOfLevelIdsToElements()
        if index != 0:
            indexOfNewLevel = None
            for i in range(index, 0, -1):
                lvlIndex = i - 1
                if startLevelOffset <= (levels[lvlIndex].Elevation - levels[index].Elevation):
                    indexOfNewLevel = lvlIndex
                else:
                    break
            if indexOfNewLevel != None:
                self.setNewBaseBoundries(index, indexOfNewLevel)

    # Sets new base boundry for element
    def setNewBaseBoundries(self, levelIndex, newLevelIndex):
        differenceInOffset = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
        newOffset = self.getBaseOffsetValue() + differenceInOffset
        newLevelId = self.levelsList[newLevelIndex]
        TransactionManager.Instance.EnsureInTransaction(doc)
        self.setBaseConstraintLevelId(self.element, newLevelId)
        self.setBaseOffsetValue(self.element, newOffset)
        TransactionManager.Instance.TransactionTaskDone()
    
    # Returns index of top level on the list of levels
    def getIndexOfTopLevel(self):
        endLevelId = self.getTopConstraintLevelId()
        return self.levelsList.index(endLevelId)

    # Returns index of base level on the list of levels
    def getIndexOfBaseLevel(self):
        startLevelId = self.getBaseConstraintLevelId()
        return self.levelsList.index(startLevelId)


class WallSplitter(ElementSplitter):

#GETTERS

    # Returns base constraint levelId
    def getBaseConstraintLevelId(self):
        return self.element.get_Parameter(db.BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()

    # Returns base offset value
    def getBaseOffsetValue(self):
        return self.element.get_Parameter(db.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()

    # Returns unconnected height
    def getHeight(self):
        return self.element.get_Parameter(db.BuiltInParameter.WALL_USER_HEIGHT_PARAM).AsDouble()

    # Returns top constraint levelId
    def getTopConstraintLevelId(self):
        return self.element.get_Parameter(db.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()

    # Returns top offset value
    def getTopOffsetValue(self):
        return self.element.get_Parameter(db.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()

# SETTERS

    # Void, sets base constraint level based on level Id
    def setBaseConstraintLevelId(self, element, levelId):
        element.get_Parameter(db.BuiltInParameter.WALL_BASE_CONSTRAINT).Set(levelId)

    # Void,sets base offset based on value
    def setBaseOffsetValue(self, element, value):
        element.get_Parameter(db.BuiltInParameter.WALL_BASE_OFFSET).Set(value)

    # Void, sets top constraint level based on level Id
    def setTopConstraintLevelId(self, element, levelId):
        element.get_Parameter(db.BuiltInParameter.WALL_HEIGHT_TYPE).Set(levelId)

    # Void,sets top offset based on value
    def setTopOffsetValue(self, element, value):
        element.get_Parameter(db.BuiltInParameter.WALL_TOP_OFFSET).Set(value)

    # Due to openings neccessary to develop additional function
    def additionalModificationOfElement(self, elementToChange):
        objectOfOpenings = WallOpenings(self.levelsList, elementToChange, self.doc)
        objectOfOpenings.deleteOpeningsNotInWallRange()

class ColumnSplitter(ElementSplitter):

#GETTERS

    # Returns base constraint
    def getBaseConstraintLevelId(self):
        return self.element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).AsElementId()

    def getBaseOffsetValue(self):
        return self.element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).AsDouble()

    # Returns unconnected height
    def getHeight(self):
        return self.element.LookupParameter("Length").AsDouble()

    # Returns top constraint levelId
    def getTopConstraintLevelId(self):
        return self.element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).AsElementId()

    # Returns top offset value
    def getTopOffsetValue(self):
        return self.element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).AsDouble()

# SETTERS

    # Void, sets base constraint level based on level Id
    def setBaseConstraintLevelId(self, element, levelId):
        element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).Set(levelId)

    # Void,sets base offset based on value
    def setBaseOffsetValue(self, element, value):
        element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).Set(value)

    # Void, sets top constraint level based on level Id
    def setTopConstraintLevelId(self, element, levelId):
        element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(levelId)

    # Void,sets top offset based on value
    def setTopOffsetValue(self, element, value):
        element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(value)

class SlantedColumnSplitter(ColumnSplitter):

#GETTERS  - inherits from parent
    
    # Gets data from splitting element
    def getElementData(self):
        self.param_Mark = self.element.LookupParameter("Mark").AsString()
        self.param_BaseCutStyle = self.element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_BASE_CUT_STYLE).AsInteger()
        self.param_TopCutStyle = self.element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_TOP_CUT_STYLE).AsInteger()

# SETTERS - inherits from parent
    
    # Sets basic parameters to newly created elements
    def setElementData(self, element):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        try:
            element.LookupParameter("Mark").Set(self.param_Mark)
        # pass while mark == None
        except TypeError:
            pass
        element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_BASE_CUT_STYLE).Set(self.param_BaseCutStyle)
        element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_TOP_CUT_STYLE).Set(self.param_TopCutStyle)
        TransactionManager.Instance.TransactionTaskDone()

    # Gets difference between start and end point Z Coordinate
    def getElementVerticalHeight(self, element):
        if type(element) == db.ElementId:
            element = self.doc.GetElement(element)
        elementCurve = element.Location.Curve
        return elementCurve.GetEndPoint(1).Z - elementCurve.GetEndPoint(0).Z

    # Splits proper levels for elements which has offset different than 0
    def setOffsetForLastElement(self, element, index, coefficient):
        if round(coefficient, 3) > 0 and round(coefficient, 3) < 1:
            self.setBaseConstraintLevelId(element, self.levelsList[index + 1])
            self.setTopConstraintLevelId(element, self.levelsList[index + 1])
        else:
            self.setBaseConstraintLevelId(element, self.levelsList[index])
            self.setTopConstraintLevelId(element, self.levelsList[index + 1])
    
    # splits slantedColumnIntoTwoElements
    def splitColumnIntoTwoElements(self, element, index, coefficinet):
        oldElement = element
        if round(coefficinet, 3) > 0 and round(coefficinet, 3) < 1:
                TransactionManager.Instance.EnsureInTransaction(self.doc)
                elementBeingSplit = self.doc.GetElement(element.Split(coefficinet))
                TransactionManager.Instance.TransactionTaskDone()
                self.setBaseConstraintLevelId(oldElement, self.levelsList[index])
                self.setTopConstraintLevelId(oldElement, self.levelsList[index + 1])
                self.setElementData(oldElement)
                return elementBeingSplit
        else:
            return element

    # Splits slanted column
    def splitElement(self):
        self.getElementData()
        if self.isElementPossibleToSplit():
            startLevelIndex = self.getIndexOfBaseLevel()
            endLevelIndex = self.getIndexOfTopLevel()
            elementBeingSplit = self.element
            for i in range(startLevelIndex, endLevelIndex):
                splitedElementLength = self.getElementVerticalHeight(elementBeingSplit)
                if i == startLevelIndex:
                    segmentLen = self.doc.GetElement(self.levelsList[i+1]).Elevation - self.doc.GetElement(self.levelsList[i]).Elevation - self.getBaseOffsetValue()
                elif i == endLevelIndex - 1:
                    segmentLen = self.doc.GetElement(self.levelsList[i+1]).Elevation - self.doc.GetElement(self.levelsList[i]).Elevation + self.getTopOffsetValue()
                else:
                    segmentLen = self.doc.GetElement(self.levelsList[i+1]).Elevation - self.doc.GetElement(self.levelsList[i]).Elevation
                coefficientOfSplitting = segmentLen/splitedElementLength
                elementBeingSplit = self.splitColumnIntoTwoElements(elementBeingSplit, i, coefficientOfSplitting)
            self.setOffsetForLastElement(elementBeingSplit, i, coefficientOfSplitting)
            self.setElementData(elementBeingSplit)

# Abstract class for MEP elements which is inherited by certain MEP categories
class MepSplitter(ElementSplitter):
    
    # Splits slanted column
    def splitElement(self):
        self.test = []
        elementsToAssignProperLevel = list()
        levels = self.convertListOfLevelIdsToElements()
        if not self.isElementPossibleToSplit():
            return None
        elementToSplit = self.element
        elementsToAssignProperLevel.append(elementToSplit)
        for level in levels:
            levelElevation = level.Elevation
            if elementToSplit == None:
                break
            elif levelElevation > self.startPoint.Z and levelElevation + 0.01 < self.endPoint.Z:
                elementToSplit = self.splitVerticalElement(elementToSplit, level, levels)
        return self.test

    def assignLevelsToElements(self, elements, levels):
        lst = list()
        for element in elements:
            lst.append(self.setBaseLevelToElement(element, levels))
        return lst


    def setBaseLevelToElement(self, element, levels):
        elementCurve = element.Location.Curve
        if self.elementLocationStyle == "TopToDown":
            elementStartPoint = elementCurve.GetEndPoint(0)
        else:
            elementStartPoint = elementCurve.GetEndPoint(1)
        return elementCurve.GetEndPoint(0)
        for level in levels:
            elevation = level.Elevation
            if levels.index(level) == 0 and elementStartPoint < elevation:
                self.setBaseConstraintLevelId(element, self.levelsList[0])

    def splitVerticalElement(self, elementToSplit, cutLevel, listOfLevels):
        tempElementCurve = elementToSplit.Location.Curve
        endPoint = tempElementCurve.GetEndPoint(1)
        startPoint = tempElementCurve.GetEndPoint(0)
        vectorFromStartPointToEndPoint = endPoint - startPoint
        proportionOfDistanceToCutLocation = math.fabs(startPoint.Z - cutLevel.Elevation)/startPoint.DistanceTo(endPoint)
        cutPoint = startPoint + vectorFromStartPointToEndPoint * proportionOfDistanceToCutLocation
        return self.cutElementAndAssignUnionsPlusLevels(elementToSplit, cutPoint, listOfLevels)

    # checkes if element is almost vertical, it check is horizontal distance ratio between top and down in order 
    # to vertical distance is less than 0.0001
    def checkIfElementIsAlmostVertical(self):
        verticalLength = math.fabs(self.endPoint.Z - self.startPoint.Z)
        horizontalLength = math.sqrt(math.fabs(self.endPoint.X - self.startPoint.X)**2 + math.fabs(self.endPoint.Y - self.startPoint.Y)**2)
        if horizontalLength/verticalLength <= 0.0001:
            return True
        else:
            return False

    # checks style of a MEP element is it model from Top to Down or from Down to Top and assignes parameter
    def isStartPointUpOrDown(self, originalStart, originalEnd):
        if originalStart.Z > originalEnd.Z:
            self.elementLocationStyle = "TopToDown"
            self.startPoint = originalEnd
            self.endPoint = originalStart
        else:
            self.elementLocationStyle = "DownToTop"
            self.startPoint = originalStart
            self.endPoint = originalEnd
           

    # checks if element goes trought more than
    def isElementPossibleToSplit(self):
        elementCurve = self.element.Location.Curve
        self.isStartPointUpOrDown(elementCurve.GetEndPoint(0), elementCurve.GetEndPoint(1))
        if not self.checkIfElementIsAlmostVertical():
            return False
        startPointLevelIndex = None
        endPointLevelIndex = None
        levels = self.convertListOfLevelIdsToElements()
        for level in levels:
            levelElevation = level.Elevation
            if self.startPoint.Z < levelElevation and self.endPoint.Z > levelElevation + 0.01:
                return True
            else:
                continue
        if self.startPoint.Z < levelElevation and self.endPoint.Z > levelElevation + 0.01:
                return True
        return False

    # tries to modify element to set level as low as it is possible
    # and reduce offset. Instead of situation: Level no 3 with offset -10m
    # it changes elements base level ie. Level no 0 with offset -50cm 
    
    #GETTERS
    # Returns base constraint levelId
    def getBaseConstraintLevelId(self):
        return self.element.get_Parameter(db.BuiltInParameter.RBS_START_LEVEL_PARAM).AsElementId()

    # Returns base offset value
    def getBaseOffsetValue(self):
        return self.element.get_Parameter(db.BuiltInParameter.RBS_START_OFFSET_PARAM).AsDouble()

    #SETTERS
    # Void, sets base constraint level based on level Id
    def setBaseConstraintLevelId(self, element, levelId):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        element.get_Parameter(db.BuiltInParameter.RBS_START_LEVEL_PARAM).Set(levelId)
        TransactionManager.Instance.TransactionTaskDone()

    # Sets new base boundry for element
    def setNewBaseBoundries(self, levelIndex, newLevelIndex):
        differenceInOffset = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
        newLevelId = self.levelsList[newLevelIndex]
        TransactionManager.Instance.EnsureInTransaction(doc)
        self.setBaseConstraintLevelId(self.element, newLevelId)
        TransactionManager.Instance.TransactionTaskDone()

    def addUnion(self, newElement, elementToSplit):
        #each pipe has 2 connectors
        for i in range(2):
            for j in range(2):
                newConnector = newElement.ConnectorManager.Lookup(i)
                oldConnector = elementToSplit.ConnectorManager.Lookup(j)
                if newConnector.Origin.IsAlmostEqualTo(oldConnector.Origin):
                    TransactionManager.Instance.EnsureInTransaction(self.doc)
                    union = self.doc.Create.NewUnionFitting(newConnector, oldConnector)
                    TransactionManager.Instance.TransactionTaskDone()
                    return union

    def tryToAssignElementsToLevelsAndAddConnectors(self, newElement, elementToSplit, listOfLevels):
        tempList = list()
        if newElement != None:
            tempList.append(self.addUnion(newElement, elementToSplit))
        self.test.append(tempList)

class DuctSplitter(MepSplitter):

    def cutElementAndAssignUnionsPlusLevels(self, elementToSplit, cutPoint, listOfLevels):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        try:
            newElementId = db.Mechanical.MechanicalUtils.BreakCurve(self.doc, elementToSplit.Id, cutPoint)
            newElement = self.doc.GetElement(newElementId)
        except:
            newElement = None
        TransactionManager.Instance.TransactionTaskDone()
        self.tryToAssignElementsToLevelsAndAddConnectors(newElement, elementToSplit, listOfLevels)
        if self.elementLocationStyle == "TopToDown":
            return newElement
        return elementToSplit


class PipeSplitter(MepSplitter):

    def cutElementAndAssignUnionsPlusLevels(self, elementToSplit, cutPoint, listOfLevels):
        TransactionManager.Instance.EnsureInTransaction(self.doc)
        try:
            newElementId = db.Plumbing.PlumbingUtils.BreakCurve(self.doc, elementToSplit.Id, cutPoint)
            newElement = self.doc.GetElement(newElementId)
        except:
            newElement = None
        TransactionManager.Instance.TransactionTaskDone()
        self.tryToAssignElementsToLevelsAndAddConnectors(newElement, elementToSplit, listOfLevels)
        if self.elementLocationStyle == "TopToDown":
            return newElement
        return elementToSplit


def getlistOfElements():
    try:
        numberOfElements = len(IN[0])
        if numberOfElements > 1:
            return IN[0]
        else:
            return [IN[0]]
    except:
        return [IN[0]]

levels = getListOfLevelIds(doc)
lst = list()

for element in getlistOfElements():
    # converts dynamo element to revit element
    try:
    	revitElement = doc.GetElement(db.ElementId(element.Id))
    except AttributeError:
    	continue    	
    # gets revit element type
    try:
        elementType = revitElement.GetType()
    except TypeError:
        elementType = None
    
    element = None
    if elementType == db.Wall:
        element = WallSplitter(doc, revitElement, levels)
    elif elementType == db.FamilyInstance:
        structuralType = revitElement.StructuralType
        if structuralType == db.Structure.StructuralType.Column and not revitElement.IsSlantedColumn:
            element = ColumnSplitter(doc, revitElement, levels)
        elif structuralType == db.Structure.StructuralType.Column and revitElement.IsSlantedColumn:
            element = SlantedColumnSplitter(doc, revitElement, levels)
    elif elementType == db.Mechanical.Duct:
        element = DuctSplitter(doc, revitElement, levels)
    elif elementType == db.Plumbing.Pipe:
        element = PipeSplitter(doc, revitElement, levels)
    if element != None:
        lst.append(element.splitElement())


OUT = "done"