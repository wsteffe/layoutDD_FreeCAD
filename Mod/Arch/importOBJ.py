#***************************************************************************
#*   Copyright (c) 2011 Yorik van Havre <yorik@uncreated.net>              *
#*                                                                         *
#*   This program is free software; you can redistribute it and/or modify  *
#*   it under the terms of the GNU Lesser General Public License (LGPL)    *
#*   as published by the Free Software Foundation; either version 2 of     *
#*   the License, or (at your option) any later version.                   *
#*   for detail see the LICENCE text file.                                 *
#*                                                                         *
#*   This program is distributed in the hope that it will be useful,       *
#*   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
#*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
#*   GNU Library General Public License for more details.                  *
#*                                                                         *
#*   You should have received a copy of the GNU Library General Public     *
#*   License along with this program; if not, write to the Free Software   *
#*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
#*   USA                                                                   *
#*                                                                         *
#***************************************************************************

import os
import codecs
import ntpath
from collections import defaultdict
# import numpy as np

import FreeCAD
import Arch
import Draft
import DraftGeomUtils
import Mesh
import MeshPart
import Part

if FreeCAD.GuiUp:
    from draftutils.translate import translate
    import FreeCADGui
else:
    # \cond
    def translate(context,text):
        return text
    # \endcond

## @package importOBJ
#  \ingroup ARCH
#  \brief OBJ file format exporter
#
#  This module provides tools to import & export OBJ files.
#  It is an alternative to the standard Mesh OBJ exporter
#  and supports exporting faces with more than 3 vertices
#  and supports object colors / materials

p = Draft.precision()

if open.__module__ in ['__builtin__','io']:
    pythonopen = open

def findVert(aVertex,aList):
    "finds aVertex in aList, returns index"
    for i in range(len(aList)):
        if round(aVertex.X,p) == round(aList[i].X,p):
            if round(aVertex.Y,p) == round(aList[i].Y,p):
                if round(aVertex.Z,p) == round(aList[i].Z,p):
                    return i
    return None

def getIndices(shape,offsetv,offsetvn,colors,dosegment):
    vlist = []
    vnlist = []
    elist = []
    flist = []
    if dosegment:
        segments = defaultdict(list)
    else:
        segments = None
    mesh = None

    if not isinstance(colors, list):
        colors = []

    if isinstance(shape,Part.Shape):
        mesh = Arch.triangulate(shape,dosegment)
        if mesh.countSegments() and mesh.countSegments() == len(colors):
            for i,c in enumerate(colors):
                mesh.setSegmentColor(i, c[:3])
    elif isinstance(shape,Mesh.Mesh):
        mesh = shape

    if mesh:
        topology = mesh.Topology
        for v in topology[0]:
            vlist.append(" "+str(round(v[0],p))+" "+str(round(v[1],p))+" "+str(round(v[2],p)))

        for vn in mesh.Facets:
            vnlist.append(" "+str(vn.Normal[0]) + " " + str(vn.Normal[1]) + " " + str(vn.Normal[2]))

        for i, vn in enumerate(topology[1]):
            flist.append(" "+str(vn[0]+offsetv)+"//"+str(i+offsetvn)+\
                         " "+str(vn[1]+offsetv)+"//"+str(i+offsetvn)+\
                         " "+str(vn[2]+offsetv)+"//"+str(i+offsetvn)+" ")

        if dosegment and mesh.countSegments():
            for i in range(0, mesh.countSegments()):
                color = mesh.getSegmentColor(i)
                segments[color] += mesh.getSegment(i)

    return vlist,vnlist,elist,flist,segments


def export(exportList,filename,colors=None):
    """export(exportList,filename,colors=None):
    Called when freecad exports a file. exportList is a list
    of objects, filename is the .obj file to export (a .mtl
    file with same name will also be created together), and
    optionally colors can be a dict containing ["objectName:colorTuple"]
    pairs for use in non-GUI mode."""

    colorMap = {}
    if colors and exportList:
        doc = exportList[0].Document
        for name, c in colors.items():
            try:
                if '#' not in name:
                    colorMap[doc.getObject(name).FullName] = c
            except Exception:
                pass

    if exportList:
        _export({(o,'') for o in exportList}, filename, colorMap)
    else:
        FreeCAD.Console.PrintError("No shape selected for export\n")


def exportSelection(filename, colors=None):
    """exportSelection(filename,colors=None):

    New style exporter function called by freecad to export current selection.
    It is added to allow the function to extract object hierarchy from the
    current selection to derived to correct global placement.

    filename is the .obj file to export (a .mtl file with same name will also be
    created together), and optionally colors can be a dict containing
    ["obj_full_name:colorTuple"] pairs for use in non-GUI mode."""

    objset = set()
    for sel in FreeCADGui.Selection.getSelectionEx('*', 0):
        subs = sel.SubElementNames
        if not subs:
            objset.add((sel.Object, ''))
            continue
        for sub in subs:
            objset.add((sel.Object, Part.splitSubname(sub)[0]))
    if objset:
        _export(objset, filename, colors)
    else:
        FreeCAD.Console.PrintError("No shape selected for export\n")

def _export(exportSet, filename, colors):
    '''Internal function used to export a list of object to OBJ format.

       exportSet : a set of (obj, subname)
       filename : output file name
       colors: dict(obj_full_name, color/colors)
    '''
    import codecs
    outfile = codecs.open(filename,"wb",encoding="utf8")
    ver = FreeCAD.Version()
    outfile.write("# FreeCAD v" + ver[0] + "." + ver[1] + " build" + ver[2] + " Arch module\n")
    outfile.write("# http://www.freecad.org\n")
    offsetv = 1
    offsetvn = 1

    param = FreeCAD.ParamGet("User parameter:BaseApp/Preferences/Mod/Arch")
    # DAE and OBJ format share the same parameters
    dosegment = param.GetBool("ColladaExportSegments", False)

    exportList = list(exportSet)
    objectslist = Draft.get_group_contents(exportList, walls=True,
                                           addgroups=True)
    objectslist = Arch.pruneIncluded(objectslist)

    filenamemtl = filename[:-4] + ".mtl"
    materials = []
    outfile.write("mtllib " + os.path.basename(filenamemtl) + "\n")

    if colors is None:
        colors = {}

    tmpobj = None
    mat0 = FreeCAD.Matrix()
    namemap = defaultdict(list)
    for parentobj, sub in objectslist:
        sobj, mat = parentobj.getSubObject(sub, retType=1, matrix=mat0)

        if not sobj:
            FreeCAD.Console.PrintWarning(translate("Arch","Cannot find sub object %s.%s\n" \
                        % (parentobj.FullName, sub)))
            continue

        obj, mat = sobj.getLinkedObject(recursive=True, matrix=mat, transform=False)

        shapelist = []
        hires = None
        if FreeCAD.GuiUp:
            if (parentobj, sub) not in exportSet:
                vis = parentobj.isElementVisibleEx(sub)
                if vis == 0:
                    continue
                if vis < 0 and not sobj.ViewObject.isVisible():
                    continue

            if obj.ViewObject.DisplayMode == "HiRes":
                # check if high-resolution object is available
                if hasattr(obj,"HiRes"):
                    if obj.HiRes:
                        if obj.HiRes.isDerivedFrom("Mesh::Feature"):
                            m = obj.HiRes.Mesh
                        else:
                            m = obj.HiRes.Shape
                        hires = m.copy()
                        hires.Placement = FreeCAD.Placement(mat * m.Placement.toMatrix())
                if not hires:
                    if hasattr(obj,"CloneOf"):
                        if obj.CloneOf:
                            if hasattr(obj.CloneOf,"HiRes"):
                                if obj.CloneOf.HiRes:
                                    if obj.CloneOf.HiRes.isDerivedFrom("Mesh::Feature"):
                                        m = obj.CloneOf.HiRes.Mesh
                                    else:
                                        m = obj.CloneOf.HiRes.Shape
                                    hires = m.copy()
                                    hires.Placement = FreeCAD.Placement(
                                            mat * obj.CloneOf.Placement.toMatrix() \
                                                * m.Placement.toMatrix())
        if hires:
            shapelist.append((sobj.Label, hires, colors.get(sobj.FullName, None)))

        # DO NOT use getattr(obj, 'Mesh') because incomplete support of Mesh in
        # Link, especially link array!
        elif obj.isDerivedFrom('Mesh::Feature'):
            mesh = obj.Mesh.copy()
            mesh.Placement = FreeCAD.Placement(mat)
            color = colors.get(sobj.FullName, colors.get(obj.FullName, None))
            shapelist.append((sobj.Label, mesh, color))
        else:
            shape = Part.getShape(parentobj, sub)
            if shape.isNull():
                FreeCAD.Console.PrintError("Unable to export object %s (%s.%s), Skipping.\n" \
                                            % (sobj.Label, sobj.FullName, sub))
                continue
            else:
                facecolors = None
                color = colors.get(sobj.FullName, colors.get(obj.FullName, None))
                if color:
                    if isinstance(color[0], tuple):
                        facecolors = color
                    else:
                        facecolors = [color]

                if FreeCAD.GuiUp:
                    vobj = sobj.ViewObject
                    try:
                        # This is to make sure vobj actually owns a property
                        # called 'DiffuseColor'
                        facecolors = vobj.getPropertyByName('DiffuseColor',1)
                    except Exception:
                        # If not, then the view object is probably a link or a
                        # group. Recursive mapping of color from group is very
                        # complex. We simply copy the shape to a temporary
                        # Part::Feature, and let its view provider to do the
                        # color mapping, which is roughly equivalent of invoking
                        # Part_SimpleCopy command
                        if not tmpobj:
                            tmpDoc = FreeCAD.newDocument('_ArchTmp', hidden=True, temp=True)
                            try:
                                tmpobj = tmpDoc.removeObject('_ArchObjExport')
                            except Exception:
                                pass
                            tmpobj = tmpDoc.addObject('Part::Feature', '_ArchObjExport')
                        tmpobj.Shape = shape
                        vobj = tmpobj.ViewObject
                        vobj.mapShapeColors(sobj.Document)
                        facecolors = vobj.DiffuseColor

                if len(facecolors) <= 1 or len(facecolors) != shape.countElement('Face'):
                    shapelist.append((sobj.Label, shape, colors.get(sobj.FullName, None)))
                else:
                    shapelist.append((sobj.Label, shape, facecolors))

        for name, shape, colorlist in shapelist:
            m = False
            if hasattr(obj,"Material"):
                if obj.Material:
                    if hasattr(obj.Material,"Material"):
                        materials.append(obj.Material)
                        m = True
                        colorlist = None

            vlist,vnlist,elist,flist,segments = getIndices(
                    shape,offsetv,offsetvn,colorlist,dosegment)
            if not vlist:
                FreeCAD.Console.PrintError("Unable to export object %s (%s), Skipping.\n" \
                        % (sobj.Label, name))
                continue

            offsetv += len(vlist)
            offsetvn += len(vnlist)

            nameref = namemap[name]
            if not nameref:
                nameref.append(0)
                outfile.write("o " + name + "\n")
            else:
                nameref[0] += 1
                outfile.write("o %s_%d\n" % (name, nameref[0]))

            # write geometry
            for v in vlist:
                outfile.write("v" + v + "\n")
            for vn in vnlist:
                outfile.write("vn" + vn + "\n")
            for e in elist:
                outfile.write("l" + e + "\n")

            # write material
            if FreeCAD.GuiUp:
                shapecolor = getattr(sobj.ViewObject, 'ShapeColor', (0.8, 0.8, 0.8))
                transp = getattr(sobj.ViewObject, 'Transparency', 0.0)
            else:
                shapecolor = (0.8, 0.8, 0.8)
                transp = 0.0

            if segments:
                for i,(color,findices) in enumerate(segments.items()):
                    outfile.write('g ' + 'segment' + str(i) + '\n')
                    if not color:
                        color = shapecolor
                    mn = Draft.getrgb(color,testbw=False)[1:]
                    outfile.write("usemtl color_" + mn + "\n")
                    materials.append(("color_" + mn,color,transp))
                    for fi in findices:
                        outfile.write("f" + flist[fi] + "\n")
            else:
                if m:
                    outfile.write("usemtl " + obj.Material.Name + "\n")
                else:
                    mn = Draft.getrgb(shapecolor,testbw=False)[1:]
                    outfile.write("usemtl color_" + mn + "\n")
                    materials.append(("color_" + mn,shapecolor,transp))
                for f in flist:
                    outfile.write("f" + f + "\n")

    if tmpobj:
        tmpobj.Document.removeObject(tmpobj.Name)

    outfile.close()
    FreeCAD.Console.PrintMessage(translate("Arch","Successfully written") + " " + filename + "\n")
    if materials:
        outfile = pythonopen(filenamemtl,"w")
        outfile.write("# FreeCAD v" + ver[0] + "." + ver[1] + " build" + ver[2] + " Arch module\n")
        outfile.write("# https://www.freecad.org\n")
        kinds = {"AmbientColor":"Ka ","DiffuseColor":"Kd ","SpecularColor":"Ks ","EmissiveColor":"Ke ","Transparency":"Tr ","Dissolve":"d "}
        done = [] # store names to avoid duplicates
        for mat in materials:
            if isinstance(mat,tuple):
                if not mat[0] in done:
                    outfile.write("newmtl " + mat[0] + "\n")
                    outfile.write("Kd " + str(mat[1][0]) + " " + str(mat[1][1]) + " " + str(mat[1][2]) + "\n")
                    outfile.write("Tr " + str(mat[2]/100) + "\n")
                    outfile.write("d " + str(1-mat[2]/100) + "\n")
                    done.append(mat[0])
            else:
                if not mat.Name in done:
                    outfile.write("newmtl " + mat.Name + "\n")
                    for prop in kinds:
                        if prop in mat.Material:
                            outfile.write(kinds[prop] + mat.Material[prop].strip("()").replace(',',' ') + "\n")
                    done.append(mat.Name)
        outfile.write("# Material Count: " + str(len(materials)))
        outfile.close()
        FreeCAD.Console.PrintMessage(translate("Arch","Successfully written") + ' ' + filenamemtl + "\n")


def open(filename):
    "called when freecad wants to open a file"
    docname = (os.path.splitext(os.path.basename(filename))[0])
    doc = FreeCAD.newDocument(docname.encode("utf8"))
    doc.Label = docname
    return insert(filename,doc.Name)

def insert(filename,docname):

    meshName = ntpath.basename(filename)
    for i in meshName.split():
        if "." in i:
            i = i.split(".")[0]
    meshName = i
    "called when freecad wants to import a file"
    try:
        doc = FreeCAD.getDocument(docname)
    except NameError:
        doc = FreeCAD.newDocument(docname)
    FreeCAD.ActiveDocument = doc

    with pythonopen(filename,"r") as infile:
        verts = []
        facets = []
        activeobject = None
        material = []
        colortable = {}
        content_array = []
        for line in infile:
            content_array.append(line)
    activeobjectExists = False
    for line in content_array:
        line = line.strip()
        if line[:2] == "o ":
            activeobjectExists = True
    if not activeobjectExists:
        activeobject = meshName
    for line in content_array:
        line = line.strip()
        if line[:7] == "mtllib ":
            matlib = os.path.join(os.path.dirname(filename),line[7:])
            if os.path.exists(matlib):
                with pythonopen(matlib,"r") as matfile:
                    mname = None
                    color = None
                    trans = None
                    for mline in matfile:
                        mline = mline.strip()
                        if mline[:7] == "newmtl ":
                            if mname and color:
                                colortable[mname] = [color,trans]
                            color = None
                            trans = None
                            mname = mline[7:]
                        elif mline[:3] == "Kd ":
                            color = tuple([float(i) for i in mline[3:].split()])
                        elif mline[:2] == "d ":
                            trans = int((1-float(mline[2:]))*100)
                    if mname and color:
                        colortable[mname] = [color,trans]
        elif line[:2] == "o ":
            if activeobject:
                makeMesh(doc,activeobject,verts,facets,material,colortable)
            material = []
            facets = []
            activeobject = line[2:]
        elif line[:2] == "v ":
            verts.append([float(i) for i in line[2:].split()])
        elif line[:2] == "f ":
            fa = []
            for i in line[2:].split():
                if "/" in i:
                    i = i.split("/")[0]
                fa.append(int(i))
            facets.append(fa)
            if material:
                material[-1][-1] = len(facets)
        elif line[:7] == "usemtl ":
            material.append([line[7:], len(facets), len(facets)])
    if activeobject:
        makeMesh(doc,activeobject,verts,facets,material,colortable)
    FreeCAD.Console.PrintMessage(translate("Arch","Successfully imported") + ' ' + filename + "\n")
    return doc

def makeMesh(doc,activeobject,verts,facets,material,colortable):
    mfacets = []
    if facets:
        for facet in facets:
            if len(facet) > 3:
                vecs = [FreeCAD.Vector(*verts[i-1]) for i in facet]
                vecs.append(vecs[0])
                pol = Part.makePolygon(vecs)
                try:
                    face = Part.Face(pol)
                except Part.OCCError:
                    print("Skipping non-planar polygon:",vecs)
                else:
                    tris = face.tessellate(1)
                    for tri in tris[1]:
                        mfacets.append([tris[0][i] for i in tri])
            else:
                mfacets.append([verts[i-1] for i in facet])
    if mfacets:
        mobj = doc.addObject("Mesh::Feature",'Mesh')
        mobj.Label = activeobject
        mesh = Mesh.Mesh(mfacets)
        segments = False
        if len(material) > 1:
            err = None
            for name, begin, end in material:
                if begin == end:
                    continue
                try:
                    mesh.addSegment(range(begin, end), colortable[name][0])
                    segments = True
                except Exception as e:
                    err = str(e)
            if err:
                FreeCAD.Console.PrintError("Failed to set material: %s\n" % err)

        elif material and FreeCAD.GuiUp:
            mname = material[0][0]
            if mname in colortable:
                mobj.ViewObject.ShapeColor = colortable[mname][0]
                if colortable[mname][1] != None:
                    mobj.ViewObject.Transparency = colortable[mname][1]

        mobj.Mesh = mesh
        if segments and FreeCAD.GuiUp:
            mobj.ViewObject.highlightSegments()

