import clr
import math
from sys import path as sysPath
sysPath.append("C:\Program Files (x86)\IronPython 2.7\Lib")

# For pupose of using List[Type](iterable) 
from System.Collections.Generic import List as sysList

# Import DocumentManager and TransactionManager
clr.AddReference("RevitServices")
import RevitServices
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

# Import RevitAPI
clr.AddReference("RevitAPI")
import Autodesk.Revit.DB as db
doc = DocumentManager.Instance.CurrentDBDocument

# Static class for settings of parameters
class Settings:

	# Ratio of verticalness of an element. If condition doesn't fulfill the condition won't be splitted (no unit)
	VERTICAL_RATIO = 0.0001

	# Tolerance of level location - don't use less than 0.001 (in feets)
	ELEVATION_TOL = 0.01

	# Offset of start point from level elevation when elements is not splitted (in feets). Value can't be less than 
	# the length of longest union used in MEP models.
	OFFSET_TOLERANCE = 0.5

	# Rounding number of digits
	ROUNDING = 3

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

# Dedicated class for opening which is hosted in a wall
class WallOpenings():

	def __init__(self, levels, wall, doc):
		self.levels = levels
		self.wall = wall
		self.doc = doc
		self.getListOfOpeningsHostedInWall()
		self.createDictionaryOpeningAndItsLevel()

	# Deletes openings which are not in boundries of new/edited wall element
	def deleteOpeningsNotInWallRange(self):
		wallBaseConstrainId = self.wall.get_Parameter(db.BuiltInParameter.WALL_BASE_CONSTRAINT).AsElementId()
		wallBaseOffset = self.wall.get_Parameter(db.BuiltInParameter.WALL_BASE_OFFSET).AsDouble()
		wallTopConstrain = self.wall.get_Parameter(db.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()
		wallTopOffset = self.wall.get_Parameter(db.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()

		wallBaseElevation = self.doc.GetElement(wallBaseConstrainId).Elevation + wallBaseOffset
		wallTopElevation = self.doc.GetElement(wallTopConstrain).Elevation + wallTopOffset
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		for openingId in self.openingDictionary:
			openingElevation = self.openingDictionary[openingId]
			if openingElevation < wallBaseElevation or openingElevation > wallTopElevation:
				self.doc.Delete(openingId)
		TransactionManager.Instance.TransactionTaskDone()
		   
	# Creates list of openings elements ids and assigns it to allOpeningsId element
	def getListOfOpeningsHostedInWall(self):
		self.allOpeningsId = self.wall.GetDependentElements(db.ElementCategoryFilter(db.BuiltInCategory.OST_GenericModel))
		
	# Creates dictionary of openings. Pair is openingId : levelId
	def createDictionaryOpeningAndItsLevel(self):
		self.openingDictionary = {}
		for openingId in self.allOpeningsId:
			opening = doc.GetElement(openingId)
			self.openingDictionary[openingId] = self.getElevationOfOpening(opening)
		return self.openingDictionary

	# Returns levelId of the closest to an opening
	def getElevationOfOpening(self, opening):
		openingLevelId = opening.LookupParameter("Level").AsElementId()
		openingLevel = self.doc.GetElement(openingLevelId)
		index = self.levels.index(openingLevelId)
		try:
			openingGeneralElevation = openingLevel.Elevation + opening.LookupParameter("Elevation").AsDouble()
		except AttributeError:
			openingGeneralElevation = openingLevel.Elevation + opening.LookupParameter("Elevation from Level").AsDouble()
		return openingGeneralElevation

	# Gets level index in list of levels
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


# Abstract class - main class
class ElementSplitter():

	def __init__(self, doc, element):
		self.doc = doc
		self.element = element
		self.levelIdsList = getListOfLevelIds(doc)
		self.listLevels = self.convertListOfLevelIdsToElements()
		self.listOfElements = list()
	
	# Lanuch function which tries to modify offsets
	def modifyLevelsAndOffsets(self):
		self.tryToModifyBaseBoundries()
		self.tryToModifyTopBoundries()
	
	# Gets data from splitting element
	# For custom configuration
	def getElementData(self):
		self.param_Mark = self.element.LookupParameter("Mark").AsString()
	
	# Sets basic parameters to newly created elements
	# For custom configuration
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
		elementIdsCollection = db.ElementTransformUtils.CopyElement(self.doc, self.element.Id, db.XYZ(0,0,0))
		TransactionManager.Instance.TransactionTaskDone()
		# new is type of  ICollection<ElementId>, that is why have to convert it into list and get first element, 
		# because only one element is copying 
		return self.doc.GetElement(elementIdsCollection[0])

	# Deletes element
	def deleteOriginalElement(self):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		self.doc.Delete(self.element.Id)
		TransactionManager.Instance.TransactionTaskDone()

	# Additional element for columns with top offset
	def additionalElementWhileTopOffset(self, index):
		if self.getTopOffsetValue() != 0:
			element = self.copyElement()
			self.setBaseOffsetValue(element, 0)
			self.setTopOffsetValue(element, self.getTopOffsetValue())
			self.setBaseLevel(element, self.levelIdsList[index + 1])
			self.setTopLevel(element, self.levelIdsList[index + 1])
			self.additionalModificationOfElement(element)
			return element

	def createGroup(self):
		lst = list()
		for el in self.listOfElements:
			lst.append(el.Id)
		newList = sysList[db.ElementId](lst)
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		self.doc.Create.NewGroup(newList)
		TransactionManager.Instance.TransactionTaskDone()

	# General function for splitting elements
	def splitElement(self):
		self.getElementData()
		if self.isElementPossibleToSplit():
			self.listOfElementsToJoin = list()
			startLevelIndex = self.getIndexOfBaseLevel()
			endLevelIndex = self.getIndexOfTopLevel()
			for i in range(startLevelIndex, endLevelIndex):
				elementToChange = self.copyElement()
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
				self.setBaseLevel(elementToChange, self.levelIdsList[i])
				self.setTopLevel(elementToChange, self.levelIdsList[i+1])
				self.additionalModificationOfElement(elementToChange)
				self.listOfElements.append(elementToChange)
			self.joinElementsInList()
			self.deleteOriginalElement()
			if IN[2]:
				self.createGroup()
	
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
		try:
			self.modifyLevelsAndOffsets()
			startLevelIndex = self.getIndexOfBaseLevel()
			endLevelIndex = self.getIndexOfTopLevel()
			if startLevelIndex + 1 == endLevelIndex:
				return False
			else:
				return True
		except:
			return False
		
	# Calculates distance between levels
	def getDistanceBetweenLevels(self, originalLevelIndex, newLevelIndex):
		listOfLevels = self.convertListOfLevelIdsToElements()
		return listOfLevels[originalLevelIndex].Elevation - listOfLevels[newLevelIndex].Elevation

	# Converts list of levels ids to elements
	def convertListOfLevelIdsToElements(self):
		lst = list()
		for levelId in self.levelIdsList:
			lst.append(self.doc.GetElement(levelId))
		return lst

	# tries to modify element to set level as high as it is possible
	# and reduce offset. Instead of situation: Level no 3 with offset 10m
	# it changes elements base level ie. Level no 5 with offset -50cm 
	def tryToModifyTopBoundries(self):
		lst = list()
		levels = self.convertListOfLevelIdsToElements()
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
		elementElevation = levels[index].Elevation + endLevelOffset
		indexOfNewLevel = None
		for i in range(len(levels)):
			if levels[i].Elevation <= elementElevation:
				indexOfNewLevel = i
				lst.append(indexOfNewLevel)
			else:
				break
		if indexOfNewLevel != None:
			return self.setNewTopBoundries(index, indexOfNewLevel)

	# Sets new top boundry for element
	def setNewTopBoundries(self, levelIndex, newLevelIndex):
		offsetDifference = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
		# if wall is unconnected
		if self.getTopConstraintLevelId().IntegerValue == -1:
			newOffset = self.getHeight() + self.getBaseOffsetValue() + offsetDifference
		# Top is constrained to level
		else:
			newOffset = self.getTopOffsetValue() + offsetDifference
		newLevelId = self.levelIdsList[newLevelIndex]
		TransactionManager.Instance.EnsureInTransaction(doc)
		self.setTopLevel(self.element, newLevelId)
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
		offsetDifference = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
		newOffset = self.getBaseOffsetValue() + offsetDifference
		newLevelId = self.levelIdsList[newLevelIndex]
		TransactionManager.Instance.EnsureInTransaction(doc)
		self.setBaseLevel(self.element, newLevelId)
		self.setBaseOffsetValue(self.element, newOffset)
		TransactionManager.Instance.TransactionTaskDone()
	
	# Returns index of top level on the list of levels
	def getIndexOfTopLevel(self):
		endLevelId = self.getTopConstraintLevelId()
		return self.levelIdsList.index(endLevelId)

	# Returns index of base level on the list of levels
	def getIndexOfBaseLevel(self):
		startLevelId = self.getBaseConstraintLevelId()
		return self.levelIdsList.index(startLevelId)


# Class for walls
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

	# Sets base constraint level based on level Id
	def setBaseLevel(self, element, levelId):
		element.get_Parameter(db.BuiltInParameter.WALL_BASE_CONSTRAINT).Set(levelId)

	# Void,sets base offset based on value
	def setBaseOffsetValue(self, element, value):
		element.get_Parameter(db.BuiltInParameter.WALL_BASE_OFFSET).Set(value)

	# Sets top constraint level based on level Id
	def setTopLevel(self, element, levelId):
		element.get_Parameter(db.BuiltInParameter.WALL_HEIGHT_TYPE).Set(levelId)

	# Void,sets top offset based on value
	def setTopOffsetValue(self, element, value):
		element.get_Parameter(db.BuiltInParameter.WALL_TOP_OFFSET).Set(value)

	# Due to openings neccessary to develop additional function
	def additionalModificationOfElement(self, elementToChange):
		objectOfOpenings = WallOpenings(self.levelIdsList, elementToChange, self.doc)
		objectOfOpenings.deleteOpeningsNotInWallRange()


# Class for structural columns and columns
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

	# Sets base constraint level based on level Id
	def setBaseLevel(self, element, levelId):
		element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM).Set(levelId)

	# Sets base offset based on value
	def setBaseOffsetValue(self, element, value):
		element.get_Parameter(db.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM).Set(value)

	# Sets top constraint level based on level Id
	def setTopLevel(self, element, levelId):
		element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(levelId)

	# Sets top offset based on value
	def setTopOffsetValue(self, element, value):
		element.get_Parameter(db.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(value)


# Class for slanted columns
class SlantedColumnSplitter(ColumnSplitter):

#GETTERS  - inherits from parent
	
	# Gets data from splitting element
	def getElementData(self):
		self.param_Mark = self.element.LookupParameter("Mark").AsString()
		self.param_BaseCutStyle = self.element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_BASE_CUT_STYLE).AsInteger()
		self.param_TopCutStyle = self.element.get_Parameter(db.BuiltInParameter.SLANTED_COLUMN_TOP_CUT_STYLE).AsInteger()

# SETTERS - inherits from parent
	
	# Method prepared for copying all necessary element data. Currently Mark and cut style of top and base
	# Sets element data got in getElementData
	def setElementData(self, element):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		try:
			element.LookupParameter("Mark").Set(self.param_Mark)
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
		if round(coefficient, Settings.ROUNDING) > 0 and round(coefficient, Settings.ROUNDING) < 1:
			self.setBaseLevel(element, self.levelIdsList[index + 1])
			self.setTopLevel(element, self.levelIdsList[index + 1])
		else:
			self.setBaseLevel(element, self.levelIdsList[index])
			self.setTopLevel(element, self.levelIdsList[index + 1])
	
	# Split slanted column by coefficient which defines ratio between start and end point of column.
	# Returns part of eleemnt which is furthure iterated to split entire column
	def splitSlanterColumn(self, element, index, coefficient):
		oldElement = element
		if round(coefficient, Settings.ROUNDING) > 0 and round(coefficient, Settings.ROUNDING) < 1:
			TransactionManager.Instance.EnsureInTransaction(self.doc)
			elementBeingSplit = self.doc.GetElement(element.Split(coefficient))
			TransactionManager.Instance.TransactionTaskDone()
			self.setBaseLevel(oldElement, self.levelIdsList[index])
			self.setTopLevel(oldElement, self.levelIdsList[index + 1])
			self.setElementData(oldElement)
			return elementBeingSplit
		else:
			return element

	# Splits slanded column by intersections with all levels
	def splitElement(self):
		self.getElementData()
		if self.isElementPossibleToSplit():
			startLevelIndex = self.getIndexOfBaseLevel()
			endLevelIndex = self.getIndexOfTopLevel()
			elementBeingSplit = self.element
			self.listOfElements.append(self.element)
			for i in range(startLevelIndex, endLevelIndex):
				lowerLevel = self.doc.GetElement(self.levelIdsList[i+1]).Elevation
				higherLevel = self.doc.GetElement(self.levelIdsList[i]).Elevation
				if i == startLevelIndex:
					segmentLen = lowerLevel - higherLevel - self.getBaseOffsetValue()
				elif i == endLevelIndex - 1:
					segmentLen = lowerLevel - higherLevel + self.getTopOffsetValue()
				else:
					segmentLen = lowerLevel - higherLevel
				splittingRatio = segmentLen/self.getElementVerticalHeight(elementBeingSplit)
				elementBeingSplit = self.splitSlanterColumn(elementBeingSplit, i, splittingRatio)
				self.listOfElements.append(elementBeingSplit)
			try:
				self.setOffsetForLastElement(elementBeingSplit, i, splittingRatio)
				self.setElementData(elementBeingSplit)
			except:
				pass
			if IN[2]:
				self.createGroup()


# Abstract class for MEP elements which is inherited by certain MEP categories
class MEPElementSplitter(ElementSplitter):
	
	# Main function which splits an element into many elements with assigned level and parameters. For electrical
	# element first think which must be done is disconnection of start and end connectors. In case of other
	# instalation it is ommited. Than function checks if is it possible to split an element if so starts iteration
	# trought list of levels to get all cut points - which are intersection points between level plane and line of
	# an element
	def splitElement(self):
		self.getConnectedElements()
		self.disconnectElement()
		if not self.isElementPossibleToSplit():
			self.setBaseLevelToElement(self.element)
		elementToSplit = self.element
		for level in self.listLevels:
			levelElevation = level.ProjectElevation
			if elementToSplit == None:
				break
			elif levelElevation > self.startPoint.Z + Settings.OFFSET_TOLERANCE and levelElevation + Settings.ELEVATION_TOL < self.endPoint.Z:
				elementToSplit = self.splitVerticalElement(elementToSplit, level)
		self.listOfElements.append(elementToSplit)
		# Additional method dedicated for conection of electrical elements due to lack of breakCurve method for electrical elements
		if self.element.GetType() == db.Electrical.CableTray or self.element.GetType() == db.Electrical.Conduit:
				self.connectElements()
		if IN[2]:
			self.createGroup()

	# Implementation in ElectricalElementsSplitter 
	def connectElements(self):
		pass
	
	# Implementation in ElectricalElementsSplitter 
	def disconnectElement(self):
		pass

	# Get connected elements to the element and adds it to a instance variable connectorsToJoin (list)
	def getConnectedElements(self):
		self.connectorsToJoin = list()
		# CableTrays always have 2 connectors
		connectorManager = self.element.ConnectorManager
		for i in range(2):
			for j in connectorManager.Lookup(i).AllRefs:
				if j.Owner.Id != self.element.Id:
					self.connectorsToJoin.append(j)

	# Assign levelId to each of MEP element in the list. levelId is assinged to level parameter of an element
	def assignLevelsToElements(self, elements):
		for element in elements:
			self.setBaseLevelToElement(element)

	# Assign levelId to an element. LevelId is assinged to level parameter of an element
	def setBaseLevelToElement(self, element):
		elementCurve = element.Location.Curve
		if self.MODELING_STYLE == "TopToDown":
			elementStartPoint = elementCurve.GetEndPoint(0)
		else:
			elementStartPoint = elementCurve.GetEndPoint(1)
		for level in self.listLevels:
			elevation = level.ProjectElevation
			if self.listLevels.index(level) == 0 and elementStartPoint < elevation:
				self.setBaseLevel(element, self.levelIdsList[0])

	# Splits element but calculated point. Point Z coordinate is calculate base on level
	def splitVerticalElement(self, elementToSplit, cutLevel):
		tempElementCurve = elementToSplit.Location.Curve
		endPoint = tempElementCurve.GetEndPoint(1)
		startPoint = tempElementCurve.GetEndPoint(0)
		vectorFromStartPointToEndPoint = endPoint - startPoint
		proportionOfDistanceToCutLocation = math.fabs(startPoint.Z - cutLevel.ProjectElevation)/startPoint.DistanceTo(endPoint)
		cutPoint = startPoint + vectorFromStartPointToEndPoint * proportionOfDistanceToCutLocation
		return self.cutElementAndAssignUnionsPlusLevels(elementToSplit, cutPoint)

	# checkes if element is almost vertical, it check is horizontal distance ratio between top and down in order 
	# to vertical distance is less than 0.0001
	def checkIfElementIsAlmostVertical(self):
		verticalLength = math.fabs(self.endPoint.Z - self.startPoint.Z)
		horizontalLength = math.sqrt(math.fabs(self.endPoint.X - self.startPoint.X)**2 + math.fabs(self.endPoint.Y - self.startPoint.Y)**2)
		try:
			if horizontalLength/verticalLength <= Settings.VERTICAL_RATIO:
				return True
			else:
				return False
		#In case if two elements are at the same elevation
		except ZeroDivisionError:
			return False

	# checks style of a MEP element is it model from Top to Down or from Down to Top and assignes parameter
	def setElementModelingStyle(self):
		location = self.element.Location.Curve
		originalStart = location.GetEndPoint(0)
		originalEnd = location.GetEndPoint(1)
		if originalStart.Z > originalEnd.Z:
			self.MODELING_STYLE = "TopToDown"
			self.startPoint = originalEnd
			self.endPoint = originalStart
		else:
			self.MODELING_STYLE = "DownToTop"
			self.startPoint = originalStart
			self.endPoint = originalEnd

	# Checks if elements is possible to split (if cuts at least one level)
	def isElementPossibleToSplit(self):
		self.setElementModelingStyle()
		if not self.checkIfElementIsAlmostVertical():
			return False
		for level in self.listLevels:
			levelElevation = level.ProjectElevation
			if self.startPoint.Z < levelElevation and self.endPoint.Z > levelElevation + Settings.ELEVATION_TOL:
				return True
			else:
				continue
		if self.startPoint.Z < levelElevation and self.endPoint.Z > levelElevation + Settings.ELEVATION_TOL:
				return True
		return False
	
	#GETTERS
	# Returns base constraint levelId
	def getBaseConstraintLevelId(self):
		return self.element.get_Parameter(db.BuiltInParameter.RBS_START_LEVEL_PARAM).AsElementId()

	# Returns base offset value
	def getBaseOffsetValue(self):
		return self.element.get_Parameter(db.BuiltInParameter.RBS_START_OFFSET_PARAM).AsDouble()

	#SETTERS
	# Sets base constraint level based on level Id
	def setBaseLevel(self, element, levelId):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		element.get_Parameter(db.BuiltInParameter.RBS_START_LEVEL_PARAM).Set(levelId)
		TransactionManager.Instance.TransactionTaskDone()
		return 

	# Sets base level to an element
	def setNewBaseBoundries(self, levelIndex, newLevelIndex):
		offsetDifference = self.getDistanceBetweenLevels(levelIndex, newLevelIndex)
		newLevelId = self.levelIdsList[newLevelIndex]
		TransactionManager.Instance.EnsureInTransaction(doc)
		self.setBaseLevel(self.element, newLevelId)
		TransactionManager.Instance.TransactionTaskDone()

	# Adds a union between connectors
	def createNewUnion(self, newConnector, oldConnector):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		# It is important due to a assignment of proper level to the newly created union
		if self.MODELING_STYLE == "TopToDown":
			union = self.doc.Create.NewUnionFitting(oldConnector, newConnector)
		else:
			union = self.doc.Create.NewUnionFitting(newConnector, oldConnector)
		TransactionManager.Instance.TransactionTaskDone()
		self.listOfElements.append(union)

	# Search for a common connector location between two elements. It runs method for creation of new union when 
	# 2 connectors in the same location are found
	def insertUnion(self, newElement, elementToSplit):
		newElementManager = newElement.ConnectorManager
		oldElementManager = elementToSplit.ConnectorManager
		# All MEP elements splitted by this script has only two connectors
		for i in range(2):
			for j in range(2):
				newConnector = newElementManager.Lookup(i)
				oldConnector = oldElementManager.Lookup(j)
				if newConnector.Origin.IsAlmostEqualTo(oldConnector.Origin):
					self.createNewUnion(newConnector, oldConnector)

	# Function returns Z coordinate of start and end point of linear MEP element
	def getStartEndZCoordinateTuple(self, element):
		elementCurve = element.Location.Curve
		point_1 = elementCurve.GetEndPoint(0).Z
		point_2 = elementCurve.GetEndPoint(1).Z
		if point_1 < point_2:
			return (point_1, point_2)
		else:
			return (point_2, point_1)

	# Assigns element to most level where it is located in a model - description of conditions inside the method
	def assignProperLevelToElement(self, element):
		# Due to modeling style TopDown or DownTop location of an element might cause issue. That is why coordinates
		# variable is created. It gets start point as a point with less Z coordinate 
		coordinates = self.getStartEndZCoordinateTuple(element)
		startPoint = coordinates[0]
		endPoint = coordinates[1]
		for level in self.listLevels:
			elevation = level.ProjectElevation
			levelIndex = self.listLevels.index(level)
			# levels are sorted by elevation in ascending order. Condition checks if start point is located close
			# to an level. If so it breaks the iteration and sets found level as host level
			if elevation + Settings.ELEVATION_TOL > startPoint and elevation - Settings.ELEVATION_TOL < startPoint:
				break
			# The same as condition for start point. But in case of end point levelIndex is decreased by one (if 
			# levelIndex != 0), because element has its start point somewhere between levelIndex and levelIndex - 1,
			# so levelIndex - 1 is choosen.
			elif elevation + Settings.ELEVATION_TOL > endPoint and elevation - Settings.ELEVATION_TOL < endPoint:
				if levelIndex != 0 and not (startPoint > elevation and endPoint >= elevation):
					levelIndex = levelIndex - 1
				break
		self.setBaseLevel(element, self.levelIdsList[levelIndex])

	# The method assigns elements into level where they belongs to. Moreover after assignment it runs addUnion
	# method which connect the elements. 
	def assignElementsToLevelsAndAddUnion(self, newElement, elementToSplit):
		if elementToSplit != None:
			self.assignProperLevelToElement(elementToSplit)
		if newElement != None:
			self.assignProperLevelToElement(newElement)
		if newElement != None:
			self.insertUnion(newElement, elementToSplit)


# Class dedicated for Ducts. 
# Inheritst from ElementSplitter -> MEPElementSplitter -> DuctSplitter
class DuctSplitter(MEPElementSplitter):

	# Function splits duct into two elements. Returning element which might require further splitting
	def cutElementAndAssignUnionsPlusLevels(self, elementToSplit, cutPoint):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		newElementId = db.Mechanical.MechanicalUtils.BreakCurve(self.doc, elementToSplit.Id, cutPoint)
		newElement = self.doc.GetElement(newElementId)
		self.listOfElements.append(newElement)
		TransactionManager.Instance.TransactionTaskDone()
		self.assignElementsToLevelsAndAddUnion(newElement, elementToSplit)
		if self.MODELING_STYLE == "TopToDown":
			return newElement
		return elementToSplit


# Class dedicated for Pipes (not conduits). 
# Inheritst from ElementSplitter -> MEPElementSplitter -> PipeSplitter
class PipeSplitter(MEPElementSplitter):

	# Function splits pipe into two elements. Returning element which might require further splitting
	def cutElementAndAssignUnionsPlusLevels(self, elementToSplit, cutPoint):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		newElementId = db.Plumbing.PlumbingUtils.BreakCurve(self.doc, elementToSplit.Id, cutPoint)
		newElement = self.doc.GetElement(newElementId)
		self.listOfElements.append(newElement)
		TransactionManager.Instance.TransactionTaskDone()
		self.assignElementsToLevelsAndAddUnion(newElement, elementToSplit)
		if self.MODELING_STYLE == "TopToDown":
			return newElement
		return elementToSplit


# Class dedicated for splitting conduits and cableTrays. 
# Inheritst from ElementSplitter -> MEPElementSplitter -> ElectricalElementsSplitter
class ElectricalElementsSplitter(MEPElementSplitter):

	# Function splits cableTray/conduit into two elements. Returning element which might require further splitting
	# Depending upon location style points are selected in 2 two ways
	def cutElementAndAssignUnionsPlusLevels(self, elementToSplit, cutPoint):
		TransactionManager.Instance.EnsureInTransaction(self.doc)
		if self.MODELING_STYLE == "TopToDown":
			elementToSplitLine = db.Line.CreateBound(self.element.Location.Curve.GetEndPoint(0), cutPoint)
			newElementLine = db.Line.CreateBound(cutPoint, self.element.Location.Curve.GetEndPoint(1))
		else:
			elementToSplitLine = db.Line.CreateBound(cutPoint, self.element.Location.Curve.GetEndPoint(1))
			newElementLine = db.Line.CreateBound(self.element.Location.Curve.GetEndPoint(0), cutPoint)
		newElement = self.copyElement()
		self.listOfElements.append(newElement)
		elementToSplit.Location.Curve = elementToSplitLine
		newElement.Location.Curve = newElementLine
		self.assignElementsToLevels(elementToSplit, newElement)
		TransactionManager.Instance.TransactionTaskDone()
		return elementToSplit

	# There is no way to predict location of union in cableTrays, that is why 
	# decided to implement additional functionality - connectElements, which does it
	# after full split of elements into sepate db.Elements
	def assignElementsToLevels(self, newElement, elementToSplit):
		if elementToSplit != None:
			self.assignProperLevelToElement(elementToSplit)
		if newElement != None:
			self.assignProperLevelToElement(newElement)

	# Adds iterate trought all created elements (cableTrays or conduits)
	# gets connectors and adds it to instance variable self.connectorsToJoin.
	def addAllConnectorsToTheList(self):
		for element in self.listOfElements:
			connectorsList = list(element.ConnectorManager.Connectors)
			for connector in connectorsList:
				self.connectorsToJoin.append(connector)

	# Connects all newly created cableTray/Conduit elements. Method is sorts connectors ordered by elevation and tries 
	# to insert union. If insertion of union returns exception it means there is required connection with fitting - so
	# union is not necessary
	def connectElements(self):
		self.addAllConnectorsToTheList()
		sortedByLevel = sorted(self.connectorsToJoin, key = lambda x : x.Origin.Z)
		for connectorIndex in range(len(sortedByLevel) - 1):
			mainConnector = sortedByLevel[connectorIndex]
			# Get next item in list
			connectorToCheck = sortedByLevel[connectorIndex + 1]
			if mainConnector.Origin.IsAlmostEqualTo(connectorToCheck.Origin):
				try:
					if self.MODELING_STYLE == "TopToDown":
						self.createNewUnion(connectorToCheck, mainConnector)
					else:
						self.createNewUnion(mainConnector, connectorToCheck)
				except:
					TransactionManager.Instance.EnsureInTransaction(self.doc)
					mainConnector.ConnectTo(connectorToCheck)
					TransactionManager.Instance.TransactionTaskDone


	# Disconnects electrical elements from fitting for splitting process. The method is neccessary, because otherwise
	# top elements remembers and holds connection with fitting
	def disconnectElement(self):
		connectorManager = self.element.ConnectorManager
		for connectorIndex in range(2):
			connectorOfOriginalElement = connectorManager.Lookup(connectorIndex)
			for connectorToDisconnect in self.connectorsToJoin:
				if connectorOfOriginalElement.IsConnectedTo(connectorToDisconnect):
					TransactionManager.Instance.EnsureInTransaction(self.doc)
					connectorOfOriginalElement.DisconnectFrom(connectorToDisconnect)
					TransactionManager.Instance.TransactionTaskDone()

# Converts selected in IN[0] node elements into list. No matter if there is only
# one or multiple input elements
def getlistOfElements():
	if hasattr(IN[0], '__iter__'):
		return IN[0]
	else:
		return [IN[0]]


# #### RUNS HERE ####
for elementToSplit in getlistOfElements():
	try:
		# Converts dynamo element into db.Element (from revit API)
		revitElement = doc.GetElement(db.ElementId(elementToSplit.Id))
	except AttributeError:
		continue		
	try:
		elementType = revitElement.GetType()
	except TypeError:
		elementType = None
	element = None
	if elementType == db.Wall:
		element = WallSplitter(doc, revitElement)
	elif elementType == db.FamilyInstance:
		# Depending upon structural type of column most suitable class is used for
		# element creation
		structuralType = revitElement.StructuralType
		if structuralType == db.Structure.StructuralType.Column and not revitElement.IsSlantedColumn:
			element = ColumnSplitter(doc, revitElement)
		elif structuralType == db.Structure.StructuralType.Column and revitElement.IsSlantedColumn:
			element = SlantedColumnSplitter(doc, revitElement)
	elif elementType == db.Mechanical.Duct:
		element = DuctSplitter(doc, revitElement)
	elif elementType == db.Plumbing.Pipe:
		element = PipeSplitter(doc, revitElement)
	elif elementType == db.Electrical.CableTray or elementType == db.Electrical.Conduit:
		element = ElectricalElementsSplitter(doc, revitElement)
	# If class instance was created element is splitted
	if element != None:
		element.splitElement()

OUT = "done"