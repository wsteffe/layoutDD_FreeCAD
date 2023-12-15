#! /ucrt64/bin/python

import sys,os
#FCpath="../salt/layoutDD/python/FreeCAD/bin"
username = os.getenv("USERNAME")
FCpath="c:/users/"+username+"/klayout/salt/layoutDD/python/FreeCAD/bin"
if not FCpath in sys.path:
   sys.path.append(FCpath)

import FreeCAD
import Part
import Import
from BOPTools.ShapeMerge import mergeShapes
from BOPTools.GeneralFuseResult import GeneralFuseResult
Import.readDXF("pippo.dxf")
    
