#bl_info = {
   # "name": "Iterative Closest Point (ICP) Registration",
   # "author": "Niels Klop, adapted by Francien Bossema",
   # "version": (3, 0),
   # "blender": (2, 90, 0),
   # "location": "View3D > Sidebar > INTACT_Registration",
   # "description": "Performs iterative closest point registration",
   # "category": "Object",
#}

import bpy
import numpy as np
import math as mt
import mathutils as mu
import copy
import os
import blf
from bpy_extras import view3d_utils

#change read me and info on buttons (3 or 4 points), see b4d

def placeSeed(context, event):
    #define selected objects
    selectedObjects = bpy.context.selected_objects
    
    #define boundary conditions
    scene = context.scene
    region = context.region
    rv3d = context.region_data
    mouseCoordinates = event.mouse_region_x, event.mouse_region_y
    
    #convert cursor location and view direction
    viewVector = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouseCoordinates)
    rayOrigin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouseCoordinates)
    rayTarget = rayOrigin + viewVector
    
    #ray cast procedure for selected objects
    successArray = []
    hitLocationArray = []
    distanceArray = []
    
    for object in selectedObjects:
        #convert to object space
        matrixInverted = object.matrix_world.inverted()
        rayOriginObject = matrixInverted @ rayOrigin
        rayTargetObject = matrixInverted @ rayTarget
        rayVectorObject = rayTargetObject - rayOriginObject
        
        #raycast procedure
        success, hitLocation, _, _ = object.ray_cast(rayOriginObject, rayVectorObject)
        
        #store success, location and distance
        successArray.append(success)
        hitLocationArray.append(hitLocation)
        distanceArray.append(np.linalg.norm(hitLocation - rayOriginObject))
        
    #if raycast successful on both objects, take the one closest to viewer
    if np.all(successArray):
        object = selectedObjects[np.argmin(distanceArray)]
        hitLocation = hitLocationArray[np.argmin(distanceArray)]
    #return nothing if no raycast hit
    elif not np.any(successArray):
        return None, None
    #in both other scenarios, only one object was hit
    else:
        object = selectedObjects[np.squeeze(np.where(successArray))]
        hitLocation = hitLocationArray[np.squeeze(np.where(successArray))]
    
    #build kd tree to get closest vertex
    tree = []
    tree = mu.kdtree.KDTree(len(object.data.vertices))
    for i, v in enumerate(object.data.vertices):
        tree.insert(v.co, i)
    tree.balance()
    
    _, seedIndex, _ = tree.find(hitLocation)
    return object, seedIndex

def drawTextCallback(context, dummy):
    #callback function for plotting seed positions
    
    for object in bpy.context.visible_objects:
        if object.get('landmarkDictionary') is not None:
            for landmark, index in object['landmarkDictionary'].items():
                vertLoc = object.matrix_world @ object.data.vertices[index].co
                vertLocOnScreen = view3d_utils.location_3d_to_region_2d(context.region, context.space_data.region_3d, vertLoc)
                blf.position(0, vertLocOnScreen[0] - 2, vertLocOnScreen[1] - 8, 0)
                blf.size(0, 20, 72)
                blf.color(0, 1, 1, 0, 1)
                blf.draw(0, '·' + landmark)
    return

class OBJECT_OT_ICPreadme_operator(bpy.types.Operator):
    """Export read me"""
    bl_idname = "object.icpreadme"
    bl_label = "Export read me"
    filepath: bpy.props.StringProperty(subtype = "FILE_PATH")

    def execute(self, context):
        readme = '*** ICP REGISTRATION READ ME ***' + '\n\n' 'The ICP Registration addon is visible in Object Mode in the Sidebar (hotkey N) > ICP Registration.' + '\n\n' 'INITIAL ALIGNMENT' + '\n' 'If the two objects differ substantially in location or rotation, a pre-alignment should be performed. Select two objects with mesh data (first selected object = moving, second selected object = fixed). Press "Place Landmarks" and place 4 or more landmarks on corresponding positions on both objects. Make sure the number of landmarks is equal. Press ENTER/RETURN to confirm. Landmarks of selected objects can be deleted by pressing the "Delete Landmarks" button. After placing landmarks on both objects, perform initial alignment by selecting "Perform Initial Alignment".' + '\n' '* Allow Scaling' + '\n' 'When ticked, the moving object is allowed to scale uniformly. Otherwise, only location and rotation are taken into account.' + '\n\n' 'ICP ALIGNMENT' + '\n' 'Select two objects with mesh data (first selected object = moving, second selected object = fixed). Make sure the settings are as desired and press "Perform ICP" to start the alignment process.' + '\n' '* Allow Scaling' + '\n' 'When ticked, the moving object is allowed to scale uniformly. Otherwise, only location and rotation are taken into account.' + '\n' '* Use Vertex Selections' + '\n' 'When ticked, only the selected vertices (in Edit Mode) are used for registration. As such, the registration can be focused on a specific region of interest.' + '\n' + '* Iterations' + '\n' 'The number of iterations used for registration. Increase to improve accuracy, decrease to improve alignment time.' + '\n' '* Outlier Percentage' + '\n' 'Fraction of outliers (non-corresponding points between the two objects). For example: when set to 25%, 75% of the best matching point pairs between the two objects is used for registration. Increase to improve registration accuracy in noisy objects, decrease if the meshes correspond to a large extent.' + '\n' '* Downsampling Percentage' + '\n' 'Fraction of downsampling for both objects. For example: when set to 25%, 75% of the total (or selected) vertex count is used for registration by means of a random sample. Increase to improve speed in objects with large meshes, decrease to improve accuracy.' + '\n\n' 'TRANSFORMATIONS' + '\n' '* Export Transformation' + '\n' 'Export the transformation matrix (location, rotation and scale) to a .txt file. The drop-down menu gives the choice to export the combined initial and ICP transformation, or only either of these.' + '\n' '* Set Transformations' + '\n' 'Set transformation of an object from .txt file. Select the object that should be transformed, press "Set Transformations" and browse for the desired .txt file.'
        
        #write readme
        file = open(self.filepath, 'w')
        file.write(readme)
        
        #reset filepath
        self.filepath = os.path.split(self.filepath)[0] + "\\"
        return {'FINISHED'}
        
    def invoke(self, context, event):
        #open explorer
        context.window_manager.fileselect_add(self)
        
        #set path and file name
        defaultFileName = 'readme.txt'
        self.filepath += defaultFileName
        return {'RUNNING_MODAL'}

class OBJECT_OT_placeLandmarks_operator(bpy.types.Operator):
    """Place at least 4 landmarks on two selected objects for initial alignment. Press ENTER/RETURN to confirm"""
    bl_idname = "object.placelandmarks"
    bl_label = "Place Landmarks"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        objects = len(bpy.context.selected_objects)
        return objects == 1 or objects == 2
    
    def modal(self, context, event):
        if event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'} #allow navigation
        elif event.type in {'RET', 'NUMPAD_ENTER'}:
            return {'FINISHED'} #confirm
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            bpy.types.SpaceView3D.draw_handler_add(drawTextCallback, (bpy.context, None), 'WINDOW', 'POST_PIXEL')
            
            object, seedIndex = placeSeed(context, event)
            
            #if landmark dictionary does not exists, make one
            if object is not None:
                if object.get('landmarkDictionary') is None:
                    object['landmarkDictionary'] = {}
            
            if seedIndex is None:  #no raycast hit
                self.report({'ERROR'}, "Cannot place landmark. Select a position on a selected object. Press ENTER/RETURN to confirm.")
            else:
                if seedIndex not in object['landmarkDictionary'].values():
                    landmark = str(len(object['landmarkDictionary']) + 1)
                    object['landmarkDictionary'].update({landmark: seedIndex})
                else:
                    self.report({'ERROR'}, "Cannot place landmark. Another landmark is already on this position.")
            
            #redraw scene
            bpy.ops.wm.redraw_timer(type = 'DRAW_WIN_SWAP', iterations = 1)
            return {'RUNNING_MODAL'}
        return {'RUNNING_MODAL'}
    
    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

class OBJECT_OT_deleteLandmarks_operator(bpy.types.Operator):
    """Delete landmarks of selected objects"""
    bl_idname = "object.deletelandmarks"
    bl_label = "Delete Landmarks"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        objects = len(bpy.context.selected_objects)
        return objects > 0
            
    def execute(self, context):
        #delete dictionary
        for object in bpy.context.selected_objects:
            if object.get('landmarkDictionary') is not None:
                del object['landmarkDictionary']
        
        #redraw scene
        bpy.ops.wm.redraw_timer(type = 'DRAW_WIN_SWAP', iterations = 1)
        return {'FINISHED'}
    
class OBJECT_OT_initialAlignment_operator(bpy.types.Operator):
    """Perform initial alignment (first selected object = moving, last selected object = fixed)"""
    bl_idname = "object.initialalignment"
    bl_label = "Perform Initial Alignment"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return len(bpy.context.selected_objects) == 2 and bpy.context.selected_objects[0].type == 'MESH' and bpy.context.selected_objects[1].type == 'MESH'
    
    def execute(self, context):
        #assign fixed object
        fixedObject = bpy.context.active_object
        
        #assign moving object
        movingObject = bpy.context.selected_objects
        movingObject.remove(fixedObject)
        movingObject = movingObject[0]
        
        #copy T0 transformations
        transformationRoughT0 = copy.deepcopy(movingObject.matrix_world)
        
        #error messages if no or inequal amount of landmarks is detected
        if fixedObject.get('landmarkDictionary') is None or movingObject.get('landmarkDictionary') is None:
            self.report({'ERROR'}, "No landmarks detected on one or both objects. Place at least 4 landmarks on both objects.")
            return {'FINISHED'}
        if len(fixedObject['landmarkDictionary']) is not len(movingObject['landmarkDictionary']):
            self.report({'ERROR'}, "Inequal amount of landmarks detected. Place at least 4 landmarks on both objects.")
            return {'FINISHED'}
        
        #build landmark matrix
        fixedArray = np.array([fixedObject.matrix_world @ fixedObject.data.vertices[index].co for index in fixedObject['landmarkDictionary'].values()])
        movingArray = np.array([movingObject.matrix_world @ movingObject.data.vertices[index].co for index in movingObject['landmarkDictionary'].values()])
        
        #calculate centroids
        fixedCentroid = np.mean(fixedArray, axis = 0)
        movingCentroid = np.mean(movingArray, axis = 0)
        
        #move arrays to origin
        fixedOrigin = fixedArray - fixedCentroid
        movingOrigin = movingArray - movingCentroid
        
        #calculate sum of squares
        fixedSumSquared = np.sum(fixedOrigin ** 2)
        movingSumSquared = np.sum(movingOrigin ** 2)
        
        #normalize arrays
        fixedNormalized = np.sqrt(fixedSumSquared)
        fixedNormOrigin = fixedOrigin / fixedNormalized
        movingNormalized = np.sqrt(movingSumSquared)
        movingNormOrigin = movingOrigin / movingNormalized
        
        #singular value decomposition
        covMatrix = np.matrix.transpose(movingNormOrigin) @ fixedNormOrigin
        U, s, Vt = np.linalg.svd(covMatrix)
        
        #scaling
        if bpy.context.scene.allowScaling:
            scalingFactor = np.sum(s) * fixedNormalized / movingNormalized
            scalingMatrix = np.eye(4)
            for i in range(3):
                scalingMatrix[i,i] *= scalingFactor
            normMatrix = np.eye(4)
            normMatrix[0:3,3] = -np.matrix.transpose(movingCentroid)
            movingObject.matrix_world = mu.Matrix(normMatrix) @ movingObject.matrix_world
            movingObject.matrix_world = mu.Matrix(scalingMatrix) @ movingObject.matrix_world
            normMatrix[0:3,3] = -normMatrix[0:3,3]
            movingObject.matrix_world = mu.Matrix(normMatrix) @ movingObject.matrix_world
                
        #rotation
        rotation3x3 = np.matrix.transpose(Vt) @ np.matrix.transpose(U)
        rotationMatrix = np.eye(4)
        rotationMatrix[0:3,0:3] = rotation3x3
        movingObject.matrix_world = mu.Matrix(rotationMatrix) @ movingObject.matrix_world
        
        #translation
        translationMatrix = np.eye(4)
        translation = movingCentroid - np.dot(fixedCentroid, rotation3x3)
        translationMatrix[0:3,3] = np.matrix.transpose(fixedCentroid - rotation3x3 @ movingCentroid)
        movingObject.matrix_world = mu.Matrix(translationMatrix) @ movingObject.matrix_world
        
        #redraw scene
        bpy.ops.wm.redraw_timer(type = 'DRAW_WIN_SWAP', iterations = 1)
        
        #remove landmark dictionaries
        bpy.ops.object.deletelandmarks()
        
        #copy T1 transformations
        transformationRoughT1 = copy.deepcopy(movingObject.matrix_world)
        
        #compute transformation matrix
        globalVars.transformationRough = transformationRoughT1 @ transformationRoughT0.inverted_safe()
        return {'FINISHED'}

class OBJECT_OT_ICP_operator(bpy.types.Operator):
    """Start iterative closest point registration (first selected object = moving, last selected object = fixed)"""
    bl_idname = "object.icp"
    bl_label = "Perform ICP"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) == 2 and bpy.context.selected_objects[0].type == 'MESH' and bpy.context.selected_objects[1].type == 'MESH'
    
    def execute(self, context):
        #assign fixed object
        fixedObject = bpy.context.active_object
        
        #vertex selections
        if bpy.context.scene.vertexSelect:
            fixedVerts = [fixedObject.matrix_world @ v.co for v in fixedObject.data.vertices if v.select]
        else:
            fixedVerts = [fixedObject.matrix_world @ v.co for v in fixedObject.data.vertices]
        
        #downsampling
        fixedDownsampleNumber = mt.ceil(((100 - bpy.context.scene.downsamplingPerc) / 100) * len(fixedVerts))
        fixedDownsampleIndices = np.random.choice(range(len(fixedVerts)), fixedDownsampleNumber, replace = False)
        fixedVerts = [fixedVerts[idx] for idx in fixedDownsampleIndices]
        
        #build kdtree
        fixedVertsTree = mu.kdtree.KDTree(len(fixedVerts))
        for fixedIndex, fixedVertex in enumerate(fixedVerts):
            fixedVertsTree.insert(fixedVertex, fixedIndex)
        fixedVertsTree.balance()
        
        #assign moving object
        movingObject = bpy.context.selected_objects
        movingObject.remove(fixedObject)
        movingObject = movingObject[0]
        
        #vertex selections
        if bpy.context.scene.vertexSelect:
            movingVertsCount = len([v for v in movingObject.data.vertices if v.select])
        else:
            movingVertsCount = len(movingObject.data.vertices)
        
        #error message if no vertices are selected
        if len(fixedVerts) == 0 or movingVertsCount == 0:
            self.report({'ERROR'}, 'No vertices selected on one or both objects. Disable "Use Vertex Selections" or make a vertex selection in Edit Mode.')
            return {'FINISHED'} 
        
        #downsampling
        movingDownsampleNumber = mt.ceil(((100 - bpy.context.scene.downsamplingPerc) / 100) * movingVertsCount)
        movingDownsampleIndices = np.random.choice(range(movingVertsCount), movingDownsampleNumber, replace = False)
        
        #copy T0 transformations
        transformationFineT0 = copy.deepcopy(movingObject.matrix_world)
        
        #icp loop
        for iteration in range(bpy.context.scene.iterations):
            #vertex selections
            if bpy.context.scene.vertexSelect:
                movingVerts = [movingObject.matrix_world @ v.co for v in movingObject.data.vertices if v.select]
            else:
                movingVerts = [movingObject.matrix_world @ v.co for v in movingObject.data.vertices]
            
            #downsampling
            movingVerts = [movingVerts[idx] for idx in movingDownsampleIndices]
            
            #nearest neighbor search
            fixedPairIndices = []
            movingPairIndices = range(len(movingVerts))
            pairDistances = []
            for vertex in range(len(movingVerts)):
                _, minIndex, minDist = fixedVertsTree.find(movingVerts[vertex])
                fixedPairIndices.append(minIndex)
                pairDistances.append(minDist)
            
            #select inliers
            pairDistancesSorted = np.argsort(pairDistances)
            pairInliers = pairDistancesSorted[range(mt.ceil((100 - bpy.context.scene.outlierPerc) / 100 * len(pairDistancesSorted)))]
            fixedPairIndices = [fixedPairIndices[idx] for idx in pairInliers]
            movingPairIndices = [movingPairIndices[idx] for idx in pairInliers]
            fixedPairVerts = [fixedVerts[idx] for idx in fixedPairIndices]
            movingPairVerts = [movingVerts[idx] for idx in movingPairIndices]
            
            #calculate centroids
            fixedCentroid = np.mean(fixedPairVerts, axis = 0)
            movingCentroid = np.mean(movingPairVerts, axis = 0)
            
            #normalize vertices
            fixedVertsNorm = fixedPairVerts - fixedCentroid
            movingVertsNorm = movingPairVerts - movingCentroid        
            
            #singular value decomposition
            covMatrix = np.matrix.transpose(movingVertsNorm) @ fixedVertsNorm
            try:
                U, _, Vt = np.linalg.svd(covMatrix)
            except:
                self.report({'ERROR'}, 'Singular value decomposition did not converge. Disable "Allow Scaling" or ensure a better initial alignment.')
                movingObject.matrix_world = transformationFineT0
                return {'FINISHED'}
                
            #scaling
            if bpy.context.scene.allowScaling:
                scalingMatrix = np.eye(4)
                scalingFactor = mt.sqrt(np.sum(fixedVertsNorm ** 2) / np.sum(movingVertsNorm ** 2))
                for i in range(3):
                    scalingMatrix[i,i] *= scalingFactor
                normMatrix = np.eye(4)
                normMatrix[0:3,3] = -np.matrix.transpose(movingCentroid)
                movingObject.matrix_world = mu.Matrix(normMatrix) @ movingObject.matrix_world
                movingObject.matrix_world = mu.Matrix(scalingMatrix) @ movingObject.matrix_world
                normMatrix[0:3,3] = -normMatrix[0:3,3]
                movingObject.matrix_world = mu.Matrix(normMatrix) @ movingObject.matrix_world
            
            #rotation
            rotation3x3 = np.matrix.transpose(Vt) @ np.matrix.transpose(U)
            rotationMatrix = np.eye(4)
            rotationMatrix[0:3,0:3] = rotation3x3
            movingObject.matrix_world = mu.Matrix(rotationMatrix) @ movingObject.matrix_world
            
            #translation
            translationMatrix = np.eye(4)
            translationMatrix[0:3,3] = np.matrix.transpose(fixedCentroid - rotation3x3 @ movingCentroid)
            movingObject.matrix_world = mu.Matrix(translationMatrix) @ movingObject.matrix_world
            
            #redraw scene
            bpy.ops.wm.redraw_timer(type = 'DRAW_WIN_SWAP', iterations = 1)
            
        #copy T1 transformations
        transformationFineT1 = copy.deepcopy(movingObject.matrix_world)
        
        #compute transformation matrix
        globalVars.transformationFine = transformationFineT1 @ transformationFineT0.inverted_safe()
        return {'FINISHED'}

class OBJECT_OT_ICPexport_operator(bpy.types.Operator):
    """Export transformations to file"""
    bl_idname = "object.icpexport"
    bl_label = "Export Transformation"
    filepath: bpy.props.StringProperty(subtype = "FILE_PATH")
    
    @classmethod
    def poll(cls, context):
        if bpy.context.scene.exportTransformation == 'combined':
            return 'transformationRough' in dir(globalVars) and 'transformationFine' in dir(globalVars)
        if bpy.context.scene.exportTransformation == 'roughAlignment':
            return 'transformationRough' in dir(globalVars)
        if bpy.context.scene.exportTransformation == 'fineAlignment':
            return 'transformationFine' in dir(globalVars)
    
    def execute(self, context):
        #rough and fine alignment
        if bpy.context.scene.exportTransformation == 'combined':
            if 'transformationRough' in dir(globalVars) and 'transformationFine' in dir(globalVars):
                transformations = globalVars.transformationFine @ globalVars.transformationRough
            
        #only rough alignment
        if bpy.context.scene.exportTransformation == 'roughAlignment':
            if 'transformationRough' in dir(globalVars):
                transformations = globalVars.transformationRough
        
        #only fine alignment
        if bpy.context.scene.exportTransformation == 'fineAlignment':
            if 'transformationFine' in dir(globalVars):
                transformations = globalVars.transformationFine
        
        #write transformations
        np.savetxt(self.filepath, np.array(transformations))
        
        #reset filepath
        self.filepath = os.path.split(self.filepath)[0] + "\\"
        return {'FINISHED'}
        
    def invoke(self, context, event):
        #open explorer
        context.window_manager.fileselect_add(self)
        
        #set path and file name
        defaultFileName = 'transformations.txt'
        self.filepath += defaultFileName
        return {'RUNNING_MODAL'}

class OBJECT_OT_ICPset_operator(bpy.types.Operator):
    """Set transformation from file"""
    bl_idname = "object.icpset"
    bl_label = "Set Transformation"
    bl_options = {'REGISTER', 'UNDO'}
    filepath: bpy.props.StringProperty(subtype = "FILE_PATH")
    
    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) == 1 and bpy.context.selected_objects[0].type == 'MESH'
    
    def execute(self, context):
        #read transformations
        transformationMatrix = mu.Matrix(np.loadtxt(self.filepath))
        
        #assign moving object
        movingObject = bpy.context.active_object
        
        #set transformations
        movingObject.matrix_world = transformationMatrix @ movingObject.matrix_world
        return {'FINISHED'}
    
    def invoke(self, context, event):
        #open explorer
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

class OBJECT_PT_ICP_panel(bpy.types.Panel):
    bl_category = "INTACT_Registration"
    bl_label = "ICP Registration"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"

    def draw(self, context):
        #readme panel
        layout = self.layout
        row = layout.row()
        row.alignment = "RIGHT"
        row.scale_x = 2
        row.operator("object.icpreadme", text = "", icon = "QUESTION")
        layout.separator()
        
        #rough alignment panel
        layout.label(text = "Initial Alignment")
        layout.operator("object.placelandmarks")
        layout.operator("object.deletelandmarks")
        layout.operator("object.initialalignment")
        layout.prop(context.scene, "allowScaling", text = "Allow Scaling")
        layout.separator()
        
        #fine alignment panel
        layout.label(text = "ICP Alignment")
        layout.operator("object.icp")
        layout.prop(context.scene, "allowScaling", text = "Allow Scaling")
        layout.prop(context.scene, "vertexSelect", text = "Use Vertex Selections")
        layout.prop(context.scene, "iterations", text = "Iterations")
        layout.prop(context.scene, "outlierPerc", text = "Outlier %")
        layout.prop(context.scene, "downsamplingPerc", text = "Downsampling %")
        
        #transformations panel
        layout.separator()
        layout.label(text = "Transformations")
        layout.prop(context.scene, "exportTransformation", text = "")
        layout.operator("object.icpexport")
        layout.operator("object.icpset")

class globalVars():
    pass

classes = (
    OBJECT_OT_placeLandmarks_operator,
    OBJECT_OT_deleteLandmarks_operator,
    OBJECT_OT_initialAlignment_operator,
    OBJECT_OT_ICP_operator,
    OBJECT_OT_ICPreadme_operator,
    OBJECT_OT_ICPexport_operator,
    OBJECT_OT_ICPset_operator)#,
    #OBJECT_PT_ICP_panel)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    #icp panel
    bpy.types.Scene.allowScaling = bpy.props.BoolProperty(
        default = False,
        description = "Allow uniform scaling of the moving object")
    bpy.types.Scene.vertexSelect = bpy.props.BoolProperty(
        default = False,
        description = "Use only selected vertices for registration")
    bpy.types.Scene.iterations = bpy.props.IntProperty(
        default = 50, min = 1,
        description = "Number of iterations")
    bpy.types.Scene.outlierPerc = bpy.props.IntProperty(
        default = 20, min = 0, max = 99,
        description = "Outlier percentage")
    bpy.types.Scene.downsamplingPerc = bpy.props.IntProperty(
        default = 0, min = 0, max = 99,
        description = "Downsampling percentage")
        
    #export transformations panel
    bpy.types.Scene.exportTransformation = bpy.props.EnumProperty(
        name = "Export Transformation",
        items = [("combined", "Combined Transformation", "Export the combined initial and ICP transformation"),
            ("roughAlignment", "Initial Transformation", "Export only the initial transformation"),
            ("fineAlignment", "ICP Transformation", "Export only the ICP transformation")])
            
    
    
def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()