# ElementSplitter

The script allows to split elements by levels using only dynamo. It performs the same action as "Split elements" option in revits but automatycally.

![alt text](https://github.com/wojciechteclaw/ElementSplitter/blob/feature_editingReadMe/static/dynamoView.png)
### Description of input nodes:
#### 1 Select model elements node - selects elements for splitting
#### 2 Boolean node - option if user want to splits elements by all levels or only by levels visible in current view
#### 3 Boolean node - option if user want to group splitted elements. In case of MEP categories group also contains unions:

## Categories:
### -Walls (without changed profile)
### -Structural Columns
### -Slanted Strcutural Columns
### -Ducts
### -Pipes
### -Conduits
### -Cable Trays

## Unions:
![alt text](https://github.com/wojciechteclaw/ElementSplitter/blob/feature_editingReadMe/static/MEPelements.png)
Unions and elements 1b, 2b, 3b, 4b are assigned to the level "Level XXX". Elements taged as 1a, 2a, 3a, 4a are assigned to Level XXX - 1.

## Division of structural elements:
![alt text](https://github.com/wojciechteclaw/ElementSplitter/blob/feature_editingReadMe/static/WallsAndColumnsSplitting.png)
In case of structural elements (Walls and Structural Columns) they won't be splitted by the first level. As in the picture above. Feel free to message me if you need to change it.


## Openings is walls
Currently script works for wall with opening modeled as generic models. Family of generic model must be prepared as generic model hosted on wall as in the picture below:
![alt text](https://github.com/wojciechteclaw/ElementSplitter/blob/feature_editingReadMe/static/Opening.png)
In developlemnt there is another version for Door and Window Categories. 

© 2021 Wojciech Tec³aw