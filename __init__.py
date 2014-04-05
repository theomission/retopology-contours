'''
Copyright (C) 2013 CG Cookie
http://cgcookie.com
hello@cgcookie.com

Created by Patrick Moore

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
    "name": "Contour Retopology Tool",
    "description": "A tool to retopologize forms quickly with contour strokes.",
    "author": "Patrick Moore",
    "version": (1, 0, 0),
    "blender": (2, 6, 8),
    "location": "View 3D > Tool Shelf",
    "warning": '',  # used for warning icon and text in addons panel
    "wiki_url": "http://cgcookie.com/blender/docs/contour-retopology/",
    "tracker_url": "https://github.com/CGCookie/script-bakery/issues?labels=Contour+Retopology&milestone=1&page=1&state=open",
    "category": "3D View"}

import sys, os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'cgc-retopology'))    

'''    
if "bpy" in locals():
    import imp
    imp.reload(contour_classes)
    imp.reload(contour_utilities)

    print("Reloaded multifiles")
    
else:
    from . import contour_classes,  contour_utilities
    
    print("Imported multifiles")
'''
import bpy
import bmesh
import blf
import math
import sys
import time
from mathutils import Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d, region_2d_to_vector_3d, region_2d_to_location_3d
import contour_utilities
from contour_classes import ContourCutLine, ExistingVertList, CutLineManipulatorWidget, PolySkecthLine, ContourCutSeries
from mathutils.geometry import intersect_line_plane, intersect_point_line
from bpy.props import EnumProperty, StringProperty,BoolProperty, IntProperty, FloatVectorProperty, FloatProperty
from bpy.types import Operator, AddonPreferences


#a place to store stokes for later
global contour_cache 
contour_cache = {}

contour_undo_cache = []

#store any temporary triangulated objects
#store the bmesh to prevent recalcing bmesh
#each time :-)
global contour_mesh_cache
contour_mesh_cache = {}

def object_validation(ob):
    
    valid = [ob.name, len(ob.data.vertices), len(ob.data.edges), len(ob.data.polygons), len(ob.modifiers)]
    
    return valid

def write_mesh_cache(orig_ob,tmp_ob, bme):
    
    #TODO try taking this out
    global contour_mesh_cache
    
    if 'valid' in contour_mesh_cache and contour_mesh_cache['valid']:
        del contour_mesh_cache['valid']
        
    valid = object_validation(orig_ob) #TODO, maybe this should be polygons
    
    contour_mesh_cache['valid'] = valid
    
    if 'bme' in contour_mesh_cache and contour_mesh_cache['bme']:
        bme_old = contour_mesh_cache['bme']
        bme_old.free()
        del contour_mesh_cache['bme']
    
    contour_mesh_cache['bme'] = bme
    
    if 'tmp' in contour_mesh_cache and contour_mesh_cache['tmp']:
        old_obj = contour_mesh_cache['tmp']
        
        #context.scene.objects.unlink(self.tmp_ob)
        me = old_obj.data
        old_obj.user_clear()
        bpy.data.objects.remove(old_obj)
        bpy.data.meshes.remove(me)
                
        del contour_mesh_cache['tmp']
        
    contour_mesh_cache['tmp'] = tmp_ob
    
def clear_mesh_cache():
    if 'valid' in contour_mesh_cache and contour_mesh_cache['valid']:
        del contour_mesh_cache['valid']
        
    if 'bme' in contour_mesh_cache and contour_mesh_cache['bme']:
        bme_old = contour_mesh_cache['bme']
        bme_old.free()
        del contour_mesh_cache['bme']
    
    if 'tmp' in contour_mesh_cache and contour_mesh_cache['tmp']:
        old_obj = contour_mesh_cache['tmp']
        bpy.data.objects.remove(old_obj)
        del contour_mesh_cache['tmp']
        
class ContourToolsAddonPreferences(AddonPreferences):
    bl_idname = __name__
    
    simple_vert_inds = BoolProperty(
            name="Simple Inds",
            default=False,
            )
    
    vert_inds = BoolProperty(
            name="Vert Inds",
            description = "Display indices of the raw contour verts",
            default=False,
            )
    
    show_verts = BoolProperty(
            name="Show Raw Verts",
            description = "Display the raw contour verts",
            default=False,
            )
    
    show_edges = BoolProperty(
            name="Show Span Edges",
            description = "Display the extracted mesh edges.  Usually only turned off for debugging",
            default=True,
            )
    
    show_cut_indices = BoolProperty(
            name="Show Cut Indices",
            description = "Display the order the operator stores cuts.  Usually only turned on for debugging",
            default=False,
            )
        
    
    show_ring_edges = BoolProperty(
            name="Show Ring Edges",
            description = "Display the extracted mesh edges.  Usually only turned off for debugging",
            default=True,
            )
    
    draw_widget = BoolProperty(
            name="Draw Widget",
            description = "Turn off to help make mockups or clean-up visualization ",
            default=True,
            )
    
    debug = IntProperty(
            name="Debug Level",
            default=1,
            min = 0,
            max = 4,
            )
    
    show_backbone = BoolProperty(
            name = "show_backbone",
            description = "Show Cut Series Backbone",
            default = False)
    
    show_nodes = BoolProperty(
            name = "show_nodes",
            description = "Show Cut Nodes",
            default = False)
    
    show_ring_inds = BoolProperty(
            name = "show_ring_inds",
            description = "Show Ring Indices",
            default = False)
    
    show_axes = BoolProperty(
            name = "show_axes",
            description = "Show Cut Axes",
            default = False)
    
    show_debug = BoolProperty(
            name="Show Debug Settings",
            description = "Show the debug settings, useful for troubleshooting",
            default=False,
            )
    
    vert_size = IntProperty(
            name="Vertex Size",
            default=3,
            min = 1,
            max = 10,
            )
    edge_thick = IntProperty(
            name="Edge Thickness",
            default=1,
            min=1,
            max=10,
            )
    
    stroke_rgb = FloatVectorProperty(name="Stroke Color", description="Color of Strokes", min=0, max=1, default=(0,0.2,1), subtype="COLOR")
    handle_rgb = FloatVectorProperty(name="Handle Color", description="Color of Stroke Handles", min=0, max=1, default=(0.6,0,0), subtype="COLOR")
    vert_rgb = FloatVectorProperty(name="Vertex Color", description="Color of Verts", min=0, max=1, default=(0,0.2,1), subtype="COLOR")
    geom_rgb = FloatVectorProperty(name="Geometry Color", description="Color For Edges", min=0, max=1, default=(0,1, .2), subtype="COLOR")
    actv_rgb = FloatVectorProperty(name="Active Color", description="Active Cut Line", min=0, max=1, default=(0.6,.2,.8), subtype="COLOR")
    
    raw_vert_size = IntProperty(
            name="Raw Vertex Size",
            default=1,
            min = 1,
            max = 10,
            )
    
    handle_size = IntProperty(
            name="Handle Vertex Size",
            default=5,
            min = 1,
            max = 10,
            )
 
    
    line_thick = IntProperty(
            name="Line Thickness",
            default=1,
            min = 1,
            max = 10,
            )
    
    stroke_thick = IntProperty(
            name="Stroke Thickness",
            description = "Width of stroke lines drawn by user",
            default=1,
            min = 1,
            max = 10,
            )
    
    auto_align = BoolProperty(
            name="Automatically Align Vertices",
            description = "Attempt to automatically align vertices in adjoining edgeloops. Improves outcome, but slows performance",
            default=True,
            )
    
    live_update = BoolProperty(
            name="Live Update",
            description = "Will live update the mesh preview when transforming cut lines.  Looks good, but can get slow on large meshes",
            default=True,
            )
    
    use_x_ray = BoolProperty(
            name="X-Ray",
            description = 'Enable X-Ray on Retopo-mesh upon creation',
            default=False,
            )
    
    use_perspective = BoolProperty(
            name="Use Perspective",
            description = 'Will cause non parallel cuts from same view',
            default=True,
            )
    
    #TODO  Theme this out nicely :-) 
    widget_color = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,0,1), subtype="COLOR")
    widget_color2 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(1,0,0), subtype="COLOR")
    widget_color3 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,1,0), subtype="COLOR")
    widget_color4 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(0,0.2,.8), subtype="COLOR")
    widget_color5 = FloatVectorProperty(name="Widget Color", description="Choose Widget color", min=0, max=1, default=(.9,.1,0), subtype="COLOR")
    
    
    widget_radius = IntProperty(
            name="Widget Radius",
            description = "Size of cutline widget radius",
            default=25,
            min = 20,
            max = 100,
            )
    
    widget_radius_inner = IntProperty(
            name="Widget Inner Radius",
            description = "Size of cutline widget inner radius",
            default=10,
            min = 5,
            max = 30,
            )
    
    widget_thickness = IntProperty(
            name="Widget Line Thickness",
            description = "Width of lines used to draw widget",
            default=2,
            min = 1,
            max = 10,
            )
    
    widget_thickness2 = IntProperty(
            name="Widget 2nd Line Thick",
            description = "Width of lines used to draw widget",
            default=4,
            min = 1,
            max = 10,
            )
        
    arrow_size = IntProperty(
            name="Arrow Size",
            default=12,
            min=5,
            max=50,
            )   
    
    arrow_size2 = IntProperty(
            name="Translate Arrow Size",
            default=10,
            min=5,
            max=50,
            )      
    vertex_count = IntProperty(
            name = "Vertex Count",
            description = "The Number of Vertices Per Edge Ring",
            default=10,
            min = 3,
            max = 250,
            )
    
    cut_count = IntProperty(
            name = "Vertex Count",
            description = "The Number of Cuts Per Guide Stroke",
            default=10,
            min = 3,
            max = 100,
            )
    
    
    cyclic = BoolProperty(
            name = "Cyclic",
            description = "Make Retopo Loops Cyclic",
            default = False)
    
    recover = BoolProperty(
            name = "Recover",
            description = "Recover strokes from last session",
            default = False)
    
    recover_clip = IntProperty(
            name = "Recover Clip",
            description = "Number of cuts to leave out, usually just 0 or 1",
            default=1,
            min = 0,
            max = 10,
            )
    
    search_factor = FloatProperty(
            name = "Search Factor",
            description = "percentage of object distance to search for new cuts",
            default=.2,
            min = 0,
            max = 1,
            )
        
    intersect_threshold = FloatProperty(
            name = "Intersect Factor",
            description = "Stringence for connecting new strokes",
            default=1.,
            min = .000001,
            max = 1,
            )
    
    merge_threshold = FloatProperty(
            name = "Intersect Factor",
            description = "distance below which to snap strokes together",
            default=1.,
            min = .000001,
            max = 1,
            )
    
    density_factor = IntProperty(
            name = "Density Factor",
            description = "Fraction of diagonal to start mesh density of poly sketch...bigger numbers = smaller quads",
            default=40,
            min = 1,
            max = 1000,
            )
    
    cull_factor = IntProperty(
            name = "Cull Factor",
            description = "Fraction of screen drawn points to throw away. Bigger = less detail",
            default = 4,
            min = 1,
            max = 10,
            )
    
    smooth_factor = IntProperty(
            name = "Smooth Factor",
            description = "Iterations to smooth drawn strokes",
            default = 5,
            min = 1,
            max = 10,
            )
    
    feature_factor = IntProperty(
            name = "Smooth Factor",
            description = "Fraction of sketch bounding box to be considered feature. Bigger = More Detail",
            default = 4,
            min = 1,
            max = 20,
            )
    
    extend_radius = IntProperty(
            name="Snap/Extend Radius",
            default=20,
            min=5,
            max=100,
            )
    sketch_color1 = FloatVectorProperty(name="sketch Color", description="Vert Color", min=0, max=1, default=(1,1,0), subtype="COLOR")
    sketch_color2 = FloatVectorProperty(name="sketch Color", description="Edge Color", min=0, max=1, default=(0,1,.1), subtype="COLOR")
    sketch_color3 = FloatVectorProperty(name="sketch Color", description="Tip Color", min=0, max=1, default=(0,.5,1), subtype="COLOR")
    sketch_color4 = FloatVectorProperty(name="sketch Color", description="Tail/Sketch Color", min=0, max=1, default=(.8,0.3,.4), subtype="COLOR")
    sketch_color5 = FloatVectorProperty(name="sketch Color", description="Highlight Color", min=0, max=1, default=(1,.1,.1), subtype="COLOR")
    
    
    
    
    def draw(self, context):
        layout = self.layout

        # Interaction Settings
        row = layout.row(align=True)
        row.prop(self, "auto_align")
        row.prop(self, "live_update")
        row.prop(self, "use_perspective")
        
        row = layout.row()
        row.prop(self, "use_x_ray", "Enable X-Ray at Mesh Creation")
        

        # Visualization Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Stroke And Loop Settings")

        row = box.row()
        row.prop(self, "stroke_rgb", text="Stroke Color")
        row.prop(self, "handle_rgb", text="Handle Color")
        row.prop(self, "actv_rgb", text="Hover Color")
        
        row = box.row()
        row.prop(self, "vert_rgb", text="Vertex Color")
        row.prop(self, "geom_rgb", text="Edge Color")
        

        row = box.row(align=False)
        row.prop(self, "handle_size", text="Handle Size")
        row.prop(self, "stroke_thick", text="Stroke Thickness")

        row = box.row(align=False)
        row.prop(self, "show_edges", text="Show Edge Loops")
        row.prop(self, "line_thick", text ="Edge Thickness")
        
        row = box.row(align=False)
        row.prop(self, "show_ring_edges", text="Show Edge Rings")
        row.prop(self, "vert_size")

        row = box.row(align=True)
        row.prop(self, "show_cut_indices", text = "Edge Indices")

        #Poly Sketch Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Poly Sketch/Stroke Settings")
        
        
        row = box.row()
        row.prop(self, "extend_radius", text="Snap Radius")
        row.prop(self, "cull_factor", text="Cull Factor")
        row.prop(self, "intersect_threshold", text="Intersection Threshold")
        row.prop(self, "density_factor", text="Density Factor")
        
        row = box.row()
        row.prop(self, "merge_threshold", text="Merge Threshold")
        row.prop(self, "smooth_factor", text="Smooth Factor")
        row.prop(self, "feature_factor", text="Smooth Factor")
        
        
        row = box.row()
        row.prop(self, "sketch_color1", text="Color 1")
        row.prop(self, "sketch_color2", text="Color 2")
        row.prop(self, "sketch_color3", text="Color 3")
        row.prop(self, "sketch_color4", text="Color 4")
        row.prop(self, "sketch_color5", text="Color 5")
            
        
        # Widget Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Widget Settings")

        row = box.row()
        row.prop(self,"draw_widget", text = "Display Widget")

        if self.draw_widget:
            row = box.row()
            row.prop(self, "widget_radius", text="Radius")
            row.prop(self,"widget_radius_inner", text="Active Radius")
            
            row = box.row()
            row.prop(self, "widget_thickness", text="Line Thickness")
            row.prop(self, "widget_thickness2", text="2nd Line Thickness")
            row.prop(self, "arrow_size", text="Arrow Size")
            row.prop(self, "arrow_size2", text="Translate Arrow Size")

            row = box.row()
            row.prop(self, "widget_color", text="Color 1")
            row.prop(self, "widget_color2", text="Color 2")
            row.prop(self, "widget_color3", text="Color 3")
            row.prop(self, "widget_color4", text="Color 4")
            row.prop(self, "widget_color5", text="Color 5")

        # Debug Settings
        box = layout.box().column(align=False)
        row = box.row()
        row.label(text="Debug Settings")

        row = box.row()
        row.prop(self, "show_debug", text="Show Debug Settings")
        
        if self.show_debug:
            row = box.row()
            row.prop(self, "debug")
            
            row = box.row()
            row.prop(self, "vert_inds", text="Show Vertex Indices")
            row.prop(self, "simple_vert_inds", text="Show Simple Indices")

            row = box.row()
            row.prop(self, "show_verts", text="Show Raw Vertices")
            row.prop(self, "raw_vert_size")
            
            row = box.row()
            row.prop(self, "show_backbone", text="Show Backbone")
            row.prop(self, "show_nodes", text="Show Cut Nodes")
            row.prop(self, "show_ring_indices", text="Show Ring Indices")
            
        
class CGCOOKIE_OT_retopo_contour_panel(bpy.types.Panel):
    '''Retopologize Forms with Contour Strokes'''
    bl_label = "Contour Retopolgy"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'

    @classmethod
    def poll(cls, context):
        mode = bpy.context.mode
        obj = context.active_object
        return (obj and obj.type == 'MESH' and mode in ('OBJECT', 'EDIT_MESH'))



    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column()
        col.operator("cgcookie.retop_contour", text="Draw Contours", icon='MESH_UVSPHERE')
        col = box.column()
        col.operator("cgcookie.clear_cache", text = "Clear Cache", icon = 'CANCEL')
        
        cgc_contour = context.user_preferences.addons['cgc-retopology'].preferences
        row = box.row()
        row.prop(cgc_contour, "cyclic")
        row.prop(cgc_contour, "vertex_count")
        
        row = box.row()
        row.prop(cgc_contour, "recover")
        row.prop(cgc_contour, "recover_clip")
        
        box = layout.box()
        row = box.row()
        row.operator("cgcookie.retopo_poly_sketch", text="Sketch Poly Strips", icon='MESH_UVSPHERE')
        
        row = box.row()
        row.prop(cgc_contour, "density_factor")

class CGCOOKIE_OT_retopo_contour_menu(bpy.types.Menu):  
    bl_label = "Retopology"
    bl_space_type = 'VIEW_3D'
    bl_idname = "object.retopology_menu"

    def draw(self, context):
        layout = self.layout

        layout.operator_context = 'INVOKE_DEFAULT'

        layout.operator("cgcookie.retop_contour", text="Draw Contours")  

class CGCOOKIE_OT_retopo_cache_clear(bpy.types.Operator):
    '''
    Removes the temporary object and mesh data from the cache.
    Do this if you have altered your original form in any way   
    '''
    bl_idname = "cgcookie.clear_cache"
    bl_label = "Clear Contour Cache" 
    
    def execute(self,context):
        
        clear_mesh_cache()
        
        return {'FINISHED'}
    
def retopo_draw_callback(self,context):
    
    settings = context.user_preferences.addons['cgc-retopology'].preferences

    stroke_color = settings.stroke_rgb
    handle_color = settings.handle_rgb
    hover_color = settings.actv_rgb
    g_color = settings.geom_rgb
    v_color = settings.vert_rgb

    if (self.post_update or self.modal_state == 'NAVIGATING') and context.space_data.use_occlude_geometry:
        for path in self.cut_paths:
            path.update_visibility(context, self.original_form)
            for cut_line in path.cuts:
                cut_line.update_visibility(context, self.original_form)
                    
        self.post_update = False
        

    for i, c_cut in enumerate(self.cut_lines):
        if self.widget_interaction and self.drag_target == c_cut:
            interact = True
        else:
            interact = False
        
        c_cut.draw(context, settings,three_dimensional = self.navigating, interacting = interact)

        if c_cut.verts_simple != [] and settings.show_cut_indices:
            loc = location_3d_to_region_2d(context.region, context.space_data.region_3d, c_cut.verts_simple[0])
            blf.position(0, loc[0], loc[1], 0)
            blf.draw(0, str(i))


    if self.cut_line_widget and settings.draw_widget:
        self.cut_line_widget.draw(context)
        
    if len(self.draw_cache):
        contour_utilities.draw_polyline_from_points(context, self.draw_cache, (1,.5,1,.8), 2, "GL_LINE_SMOOTH")
        
    if len(self.cut_paths):
        for path in self.cut_paths:
            path.draw(context, path = True, nodes = settings.show_nodes, rings = True, follows = True, backbone = settings.show_backbone    )
            
    if len(self.snap_circle):
        contour_utilities.draw_polyline_from_points(context, self.snap_circle, self.snap_color, 2, "GL_LINE_SMOOTH")
        
class CGCOOKIE_OT_retopo_contour(bpy.types.Operator):
    '''Retopologize Forms with Contour Strokes'''
    bl_idname = "cgcookie.retop_contour"
    bl_label = "Contour Retopologize"    
    
    @classmethod
    def poll(cls,context):
        if context.mode not in {'EDIT_MESH','OBJECT'}:
            return False
        
        if context.active_object:
            if context.mode == 'EDIT_MESH':
                if len(context.selected_objects) > 1:
                    return True
                else:
                    return False
            else:
                return context.object.type == 'MESH'
        else:
            return False
    
    def hover_guide_mode(self,context, settings, event):
        '''
        handles mouse selection, hovering, highlighting
        and snapping when the mouse moves in guide
        mode
        '''
        
        #identify hover target for highlighting
        if self.cut_paths != []:
            target_at_all = False
            breakout = False
            for path in self.cut_paths:
                if not path.select:
                    path.unhighlight(settings)
                for c_cut in path.cuts:                    
                    h_target = c_cut.active_element(context,event.mouse_region_x,event.mouse_region_y)
                    if h_target:
                        path.highlight(settings)
                        target_at_all = True
                        self.hover_target = path
                        breakout = True
                        break
                
                if breakout:
                    break
                                  
            if not target_at_all:
                self.hover_target = None
        
        #assess snap points
        if self.cut_paths != [] and not self.force_new:
            rv3d = context.space_data.region_3d
            breakout = False
            snapped = False
            for path in self.cut_paths:
                
                for n, end_cut in enumerate([path.cuts[0], path.cuts[-1]]):
                    
                    #potential verts to snap to
                    snaps = [v for i, v in enumerate(end_cut.verts_simple) if end_cut.verts_simple_visible[i]]
                    #the screen versions os those
                    screen_snaps = [location_3d_to_region_2d(context.region,rv3d,snap) for snap in snaps]
                    
                    mouse = Vector((event.mouse_region_x,event.mouse_region_y))
                    dists = [(mouse - snap).length for snap in screen_snaps]
                    
                    if len(dists):
                        best = min(dists)
                        if best < 2 * settings.extend_radius and best > 10: #TODO unify selection mouse pixel radius.

                            best_vert = screen_snaps[dists.index(best)]
                            view_z = rv3d.view_rotation * Vector((0,0,1))
                            if view_z.dot(end_cut.plane_no) > -.75 and view_z.dot(end_cut.plane_no) < .75:

                                imx = rv3d.view_matrix.inverted()
                                normal_3d = imx.transposed() * end_cut.plane_no
                                if n == 1:
                                    normal_3d = -1 * normal_3d
                                screen_no = Vector((normal_3d[0],normal_3d[1]))
                                angle = math.atan2(screen_no[1],screen_no[0]) - 1/2 * math.pi
                                left = angle + math.pi
                                right =  angle
                                self.snap = [path, end_cut]
                                self.snap_circle = contour_utilities.pi_slice(best_vert[0],best_vert[1],settings.extend_radius,.25 * settings.extend_radius, left,right, 20,t_fan = True)
                                self.snap_circle.append(self.snap_circle[0])
                                breakout = True
                                if best < settings.extend_radius:
                                    snapped = True
                                    self.snap_color = (1,0,0,1)
                                    
                                else:
                                    alpha = 1 - best/(2*settings.extend_radius)
                                    self.snap_color = (1,0,0,alpha)
                                    
                                break
                        
                    if breakout:
                        break
                    
            if not breakout:
                self.snap = []
                self.snap_circle = []
                    
                    
        
    def hover_loop_mode(self,context, settings, event):
        '''
        Handles mouse selection and hovering
        '''
        #identify hover target for highlighting
        if self.cut_paths != []:
            
            new_target = False
            target_at_all = False
            
            for path in self.cut_paths:
                for c_cut in path.cuts:
                    if not c_cut.select:
                        c_cut.unhighlight(settings) 
                    
                    h_target = c_cut.active_element(context,event.mouse_region_x,event.mouse_region_y)
                    if h_target:
                        c_cut.highlight(settings)
                        target_at_all = True
                         
                        if (h_target != self.hover_target) or (h_target.select and not self.cut_line_widget):
                            
                            self.hover_target = h_target
                            if self.hover_target.desc == 'CUT_LINE':

                                if self.hover_target.select:    
                                    self.cut_line_widget = CutLineManipulatorWidget(context, 
                                                                                    settings,
                                                                                    self.original_form, self.bme,
                                                                                    self.hover_target,
                                                                                    self.selected_path,
                                                                                    event.mouse_region_x,
                                                                                    event.mouse_region_y)
                                    self.cut_line_widget.derive_screen(context)
                                
                                else:
                                    self.cut_line_widget = None
                            
                        else:
                            if self.cut_line_widget:
                                self.cut_line_widget.x = event.mouse_region_x
                                self.cut_line_widget.y = event.mouse_region_y
                                self.cut_line_widget.derive_screen(context)
                    #elif not c_cut.select:
                        #c_cut.geom_color = (settings.geom_rgb[0],settings.geom_rgb[1],settings.geom_rgb[2],1)          
            if not target_at_all:
                self.hover_target = None
                self.cut_line_widget = None
                context.area.header_text_set(self.header_message)
                
    def new_path_from_draw(self,context,settings):
        '''
        package all the steps needed to make a new path
        TODO: What if errors?
        '''
        path = ContourCutSeries(context, self.draw_cache,
                                    cull_factor = settings.cull_factor, 
                                    smooth_factor = settings.smooth_factor,
                                    feature_factor = settings.feature_factor)
        
        
        path.ray_cast_path(context, self.original_form)
        path.find_knots()
        
        if self.existing_loops != [] and not self.force_new:
            for eloop in self.existing_loops:
                used = path.snap_end_to_existing(eloop)
                if used:
                    break
        
        elif self.snap != [] and not self.force_new:
            merge_series = self.snap[0]
            merge_ring = self.snap[1]
            
            path.snap_merge_into_other(merge_series, merge_ring, context, self.original_form, self.bme)
            
            return merge_series

        path.smooth_path(context, ob = self.original_form)
        path.create_cut_nodes(context)
        path.snap_to_object(self.original_form, raw = False, world = False, cuts = True)
        path.cuts_on_path(context, self.original_form, self.bme)
        path.connect_cuts_to_make_mesh(self.original_form)
        path.backbone_from_cuts(context, self.original_form, self.bme)
        path.update_visibility(context, self.original_form)
        path.cuts[-1].do_select(settings)
        
        self.cut_paths.append(path)
        

        return path
    
    def click_new_cut(self,context, settings, event):

        s_color = (settings.stroke_rgb[0],settings.stroke_rgb[1],settings.stroke_rgb[2],1)
        h_color = (settings.handle_rgb[0],settings.handle_rgb[1],settings.handle_rgb[2],1)
        g_color = (settings.actv_rgb[0],settings.actv_rgb[1],settings.actv_rgb[2],1)
        v_color = (settings.vert_rgb[0],settings.vert_rgb[1],settings.vert_rgb[2],1)

        new_cut = ContourCutLine(event.mouse_region_x, event.mouse_region_y,
                                             stroke_color = s_color,
                                             handle_color = h_color,
                                             geom_color = g_color,
                                             vert_color = v_color)
        
        
        for path in self.cut_paths:
            for cut in path.cuts:
                cut.deselect(settings)
                
        new_cut.do_select(settings)
        self.cut_lines.append(new_cut)
        
        return new_cut
    
    def release_place_cut(self,context,settings, event):
        self.selected.tail.x = event.mouse_region_x
        self.selected.tail.y = event.mouse_region_y
        
        width = Vector((self.selected.head.x, self.selected.head.y)) - Vector((self.selected.tail.x, self.selected.tail.y))
        
        #prevent small errant strokes
        if width.length < 20: #TODO: Setting for minimum pixel width
            self.cut_lines.remove(self.selected)
            self.selected = None
            return
        
        else:
            #hit the mesh for the first time
            hit = self.selected.hit_object(context, self.original_form, method = 'VIEW')
            
            if hit:
                
                self.selected.cut_object(context, self.original_form, self.bme)
                self.selected.simplify_cross(self.segments)
                self.selected.update_com()
                self.selected.update_screen_coords(context)
                
                
                self.selected.head = None
                self.selected.tail = None
                
                self.selected.geom_color = (settings.actv_rgb[0],settings.actv_rgb[1],settings.actv_rgb[2],1)
                
                if self.cut_paths != [] and not self.force_new:
                    inserted = False
                    for path in self.cut_paths:
                        if path.insert_new_cut(context, self.original_form, self.bme, self.selected):
                            #the cut belongs to the series now
                            inserted = True
                            path.connect_cuts_to_make_mesh(self.original_form)
                            path.update_visibility(context, self.original_form)
                            path.seg_lock = True
                            path.do_select(settings)
                            self.selected_path = path
                            self.cut_lines.remove(self.selected)
                            for other_path in self.cut_paths:
                                if other_path != self.selected_path:
                                    other_path.deselect(settings)
                            
                if self.cut_paths == [] or not inserted or self.force_new:
                    #create a blank segment
                    path = ContourCutSeries(context, [],
                                    cull_factor = settings.cull_factor, 
                                    smooth_factor = settings.smooth_factor,
                                    feature_factor = settings.feature_factor)
                    
                    path.insert_new_cut(context, self.original_form, self.bme, self.selected)
                    path.seg_lock = True  #for now
                    path.connect_cuts_to_make_mesh(self.original_form)
                    path.update_visibility(context, self.original_form)
                    
                    for other_path in self.cut_paths:
                        other_path.deselect(settings)
                    
                    self.cut_paths.append(path)
                    self.selected_path = path
                    path.do_select(settings)
                    
                    self.cut_lines.remove(self.selected)
            
            else:
                self.cut_lines.remove(self.selected)
                    
      
            #TODO - Extension of existing geometry
    def widget_transform(self,context,settings, event):
        
        self.cut_line_widget.user_interaction(context, event.mouse_region_x, event.mouse_region_y, shift = event.shift)    
        self.selected.cut_object(context, self.original_form, self.bme)
        self.selected.simplify_cross(self.selected_path.ring_segments)
        self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
        
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_visibility(context, self.original_form)    
    
    def guide_arrow_shift(self,context,event):
        if event.type == 'LEFT_ARROW':         
            for cut in self.selected_path.cuts:
                cut.shift += .05
                cut.simplify_cross(self.selected_path.ring_segments)
        else:
            for cut in self.selected_path.cuts:
                cut.shift += -.05
                cut.simplify_cross(self.selected_path.ring_segments)
                                
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_visibility(context, self.original_form)  

    def loop_arrow_shift(self,context,event):    
        if event.type == 'LEFT_ARROW':
            self.selected.shift += .05
            
        else:
            self.selected.shift += -.05
            
        self.selected.simplify_cross(self.selected_path.ring_segments)
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
        self.selected_path.update_visibility(context, self.original_form)
            
        #shift single ring
        context.area.header_text_set(text = self.mode +': Shift ' + str(self.selected.shift))
                                                
    def loop_align_modal(self,context, event):
        if not event.ctrl and not event.shift:
            act = 'BETWEEN'
                
        #align ahead    
        elif event.ctrl and not event.shift:
            act = 'FORWARD'
            
        #align behind    
        elif event.shift and not event.ctrl:
            act = 'BACKWARD'
            
        self.selected_path.align_cut(self.selected, mode = act, fine_grain = True)
        self.selected.simplify_cross(self.selected_path.ring_segments)
        
        self.selected_path.connect_cuts_to_make_mesh(self.original_form)
        self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
        self.selected_path.update_visibility(context, self.original_form)
            
    def loop_hotkey_modal(self,context,event):
            

        if self.hot_key == 'G':
            self.cut_line_widget = CutLineManipulatorWidget(context, self.settings, 
                                                        self.original_form, self.bme,
                                                        self.selected,
                                                        self.selected_path,
                                                        event.mouse_region_x,event.mouse_region_y,
                                                        hotkey = self.hot_key)
            self.cut_line_widget.transform_mode = 'EDGE_SLIDE'

        
        elif self.hot_key == 'R':
            #TODO...if CoM is off screen, then what?
            screen_pivot = location_3d_to_region_2d(context.region,context.space_data.region_3d,self.selected.plane_com)
            self.cut_line_widget = CutLineManipulatorWidget(context, self.settings, 
                                                        self.original_form, self.bme,
                                                        self.selected,
                                                        self.selected_path,
                                                        screen_pivot[0],screen_pivot[1],
                                                        hotkey = self.hot_key)
            self.cut_line_widget.transform_mode = 'ROTATE_VIEW'
            
        
        
        self.cut_line_widget.initial_x = event.mouse_region_x
        self.cut_line_widget.initial_y = event.mouse_region_y
        self.cut_line_widget.derive_screen(context)
                                             
    def modal(self, context, event):
        context.area.tag_redraw()
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        #Loop and Guide Mode
        #'WAITING'
        #'NAVIGATING'
        
        #Loop Mode
        #'WIDGET TRANSFORM'
        #'CUTTING'
        #'HOTKEY TRANSFORM'
        
        #Guide Mode
        #'DRAWING'
        
        if self.modal_state == 'NAVIGATING':
            
            if (event.type in {'MOUSEMOVE',
                               'MIDDLEMOUSE', 
                                'NUMPAD_2', 
                                'NUMPAD_4', 
                                'NUMPAD_6',
                                'NUMPAD_8', 
                                'NUMPAD_1', 
                                'NUMPAD_3', 
                                'NUMPAD_5', 
                                'NUMPAD_7',
                                'NUMPAD_9'} and event.value == 'RELEASE'):
            
                self.modal_state = 'WAITING'
                self.post_update = True
                context.area.header_text_set(text = 'WAITING')    
                return {'PASS_THROUGH'}
        
        if self.mode == 'LOOP':
            
            if self.modal_state == 'WAITING':
                
                if (event.type in {'ESC','RIGHT_MOUSE'} and 
                    event.value == 'PRESS'):
                    
                    context.area.header_text_set()
                    contour_utilities.callback_cleanup(self,context)
                    return {'CANCELLED'}
                
                elif (event.type == 'TAB' and 
                      event.value == 'PRESS'):
                    
                    self.mode = 'GUIDE'
                    self.selected = None
                    context.area.header_text_set(text = 'GUIDE MODE')
                
                elif (event.type in {'RET', 'NUMPAD_ENTER'} and 
                    event.value == 'PRESS'):
                    
                    back_to_edit = context.mode == 'EDIT_MESH'
                    
                    #This is wehre all the magic happens
                    for path in self.cut_paths:
                        path.push_data_into_bmesh(context, self.destination_ob, self.dest_bme, self.original_form, self.dest_me)
                        
                    if back_to_edit:
                        bmesh.update_edit_mesh(self.dest_me, tessface=False, destructive=True)
                    
                    else:
                        #write the data into the object
                        self.dest_bme.to_mesh(self.dest_me)
                    
                        #remember we created a new object
                        context.scene.objects.link(self.destination_ob)
                        
                        self.destination_ob.select = True
                        context.scene.objects.active = self.destination_ob
                        
                        if context.space_data.local_view:
                            view_loc = context.space_data.region_3d.view_location.copy()
                            view_rot = context.space_data.region_3d.view_rotation.copy()
                            view_dist = context.space_data.region_3d.view_distance
                            bpy.ops.view3d.localview()
                            bpy.ops.view3d.localview()
                            #context.space_data.region_3d.view_matrix = mx_copy
                            context.space_data.region_3d.view_location = view_loc
                            context.space_data.region_3d.view_rotation = view_rot
                            context.space_data.region_3d.view_distance = view_dist
                            context.space_data.region_3d.update()
                            
                    context.area.header_text_set()
                    contour_utilities.callback_cleanup(self,context)

                    return {'FINISHED'}
                

                    
                if event.type == 'MOUSEMOVE':
                    
                    self.hover_loop_mode(context, settings, event)

                
                elif (event.type == 'C' and
                      event.value == 'PRESS'):
                    
                    bpy.ops.view3d.view_center_cursor()
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'S' and event.value == 'PRESS':
                    if self.selected:
                        context.scene.cursor_location = self.selected.plane_com
                
                #NAVIGATION KEYS
                elif (event.type in {'MIDDLEMOUSE', 
                                    'NUMPAD_2', 
                                    'NUMPAD_4', 
                                    'NUMPAD_6',
                                    'NUMPAD_8', 
                                    'NUMPAD_1', 
                                    'NUMPAD_3', 
                                    'NUMPAD_5', 
                                    'NUMPAD_7',
                                    'NUMPAD_9'} and event.value == 'PRESS'):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    context.area.header_text_set(text = 'NAVIGATING')

                    return {'PASS_THROUGH'}
                
                #ZOOM KEYS
                elif (event.type in  {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not 
                        (event.ctrl or event.shift)):
                    
                    self.post_update = True
                    return{'PASS_THROUGH'}
                
                elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                    
                    if self.hover_target and self.hover_target != self.selected:
                        
                        self.selected = self.hover_target    
                        if not event.shift:
                            for path in self.cut_paths:
                                for cut in path.cuts:
                                        cut.deselect(settings)  
                                if self.selected in path.cuts:
                                    path.do_select(settings)
                                    self.selected_path = path
                                else:
                                    path.deselect(settings)
                        
                        #select the ring
                        self.hover_target.do_select(settings)
                        
                    
                    elif self.hover_target  and self.hover_target == self.selected:
                        
                        self.modal_state = 'WIDGET_TRANSFORM'
                        #sometimes, there is not a widget from the hover?
                        self.cut_line_widget = CutLineManipulatorWidget(context, 
                                                                        settings,
                                                                        self.original_form, self.bme,
                                                                        self.hover_target,
                                                                        self.selected_path,
                                                                        event.mouse_region_x,
                                                                        event.mouse_region_y)
                        self.cut_line_widget.derive_screen(context)
                        
                    else:
                        self.modal_state = 'CUTTING'
                        context.area.header_text_set(text = self.mode + ': CUTTING')
                        
                        #make a new cut and handle it with self.selected
                        self.selected = self.click_new_cut(context, settings, event)
                        
                        
                    return {'RUNNING_MODAL'}
                
                if self.selected:
                    #print(event.type + " " + event.value)
                    
                    #G -> HOTKEY
                    if event.type == 'G' and event.value == 'PRESS':
                        self.modal_state = 'HOTKEY_TRANSFORM'
                        self.hot_key = 'G'
                        self.loop_hotkey_modal(context,event)
                        return {'RUNNING_MODAL'}
                    #R -> HOTKEY
                    if event.type == 'R' and event.value == 'PRESS':
                        self.modal_state = 'HOTKEY_TRANSFORM'
                        self.hot_key = 'R'
                        self.loop_hotkey_modal(context,event)
                        return {'RUNNING_MODAL'}
                    
                    #X, DEL -> DELETE
                    elif event.type == 'X' and event.value == 'PRESS':
                        
                        if len(self.selected_path.cuts) > 1:
                            self.selected_path.remove_cut(context, self.original_form, self.bme, self.selected)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                        
                        else:
                            self.cut_paths.remove(self.selected_path)
                            self.selected_path = None
                            
                        self.selected = None
                        context.area.header_text_set(text = self.mode + ': DELETE')
                    
                    #S -> CURSOR SELECTED CoM
                    
                    #LEFT_ARROW, RIGHT_ARROW to shift
                    elif (event.type in {'LEFT_ARROW', 'RIGHT_ARROW'} and 
                          event.value == 'PRESS'):
                        
                        self.loop_arrow_shift(context,event)
                        
                        return {'RUNNING_MODAL'}
                    
                    elif event.type == 'A' and event.value == 'PRESS':
                    
                        self.loop_align_modal(context,event)
                        
                        return {'RUNNING_MODAL'}
                        
                    elif ((event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.ctrl) or
                          (event.type in {'NUMPAD_PLUS','NUMPAD_MINUS'} and event.value == 'PRESS') and event.ctrl):
                          
                        if not self.selected_path.ring_lock:
                            old_segments = self.selected_path.ring_segments
                            self.selected_path.ring_segments += 1 - 2 * (event.type == 'WHEELDOWNMOUSE' or event.type == 'NUMPAD_MINUS')
                            if self.selected_path.ring_segments < 3:
                                self.selected_path.ring_segments = 3
                                
                            for cut in self.selected_path.cuts:
                                new_bulk_shift = round(cut.shift * old_segments/self.selected_path.ring_segments)
                                new_fine_shift = old_segments/self.selected_path.ring_segments * cut.shift - new_bulk_shift
                                
                                
                                new_shift =  self.selected_path.ring_segments/old_segments * cut.shift
                                
                                print(new_shift - new_bulk_shift - new_fine_shift)
                                cut.shift = new_shift
                                cut.simplify_cross(self.selected_path.ring_segments)
                            
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)    
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                            
                            #distribute cut points
                            #make new cuts
                            #alignment
                            #etc
                        #else:
                            #let the user know the path is locked
                            #header message set
                        context.area.header_text_set(text = self.mode +': RING SEGMENTS')
                        return {'RUNNING_MODAL'}
                    #if hover == selected:
                        #LEFTCLICK -> WIDGET
                        
                
                        
                return {'RUNNING_MODAL'}
                        
            elif self.modal_state == 'CUTTING':
                
                if event.type == 'MOUSEMOVE':
                    #pass mouse coords to widget
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    message = self.mode + ':CUTTING: X: ' +  x + '  Y:  ' +  y
                    context.area.header_text_set(text = message)
                    
                    self.selected.tail.x = event.mouse_region_x
                    self.selected.tail.y = event.mouse_region_y
                    #self.seleted.screen_to_world(context)
                    
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    
                    #the new cut is created
                    #the new cut is assessed to be placed into an existing series
                    #the new cut is assessed to be an extension of selected gemometry
                    #the new cut is assessed to become the beginning of a new path
                    self.release_place_cut(context, settings, event)
                    
                    #we return to waiting
                    self.modal_state = 'WAITING'
                    context.area.header_text_set(text = self.mode + ': WAITING')
                    return {'RUNNING_MODAL'}
            
            
            elif self.modal_state == 'HOTKEY_TRANSFORM':
                if self.hot_key == 'G':
                    action = 'Grab'
                elif self.hot_key == 'R':
                    action = 'Rotate'
                    
                if event.shift:
                        action = 'FINE CONTROL ' + action
                
                if event.type == 'MOUSEMOVE':
                    #pass mouse coords to widget
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    message  = self.mode + ": " + action + ": X: " +  x + '  Y:  ' +  y
                    context.area.header_text_set(text = message)

                    #widget.user_interaction
                    self.cut_line_widget.user_interaction(context, event.mouse_region_x,event.mouse_region_y)
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    return {'RUNNING_MODAL'}
                
                
                #LEFTMOUSE event.value == 'PRESS':#RET, ENTER
                if (event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'} and
                    event.value == 'PRESS'):
                    #confirm transform
                    #recut, align, visibility?, and update the segment
                    self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
                    self.modal_state = 'WAITING'
                    context.area.header_text_set(text = self.mode + ': WAITING')
                    return {'RUNNING_MODAL'}
                
                if (event.type in {'ESC', 'RIGHTMOUSE'} and
                    event.value == 'PRESS'):
                    self.cut_line_widget.cancel_transform()
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected_path.align_cut(self.selected, mode = 'BETWEEN', fine_grain = True)
                    self.selected.update_com()
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    context.area.header_text_set(text = self.mode + ': WAITING')
                    self.modal_state = 'WAITING'
                    return {'RUNNING_MODAL'}
                
            
            elif self.modal_state == 'WIDGET_TRANSFORM':
                
                #MOUSEMOVE
                if event.type == 'MOUSEMOVE':
                    if event.shift:
                        action = 'FINE WIDGET'
                    else:
                        action = 'WIDGET'
                    
                    
                    self.widget_transform(context, settings, event)
                    
                    message = self.modal_state
                    context.area.header_text_set(text = message)
                    return {'RUNNING_MODAL'}
               
                elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    #destroy the widget
                    self.cut_line_widget = None
                    self.modal_state = 'WAITING'
                    self.selected_path.update_backbone(context, self.original_form, self.bme, self.selected, insert = False)
                    context.area.header_text_set(text = 'LOOP MODE: WAITING')
                    return {'RUNNING_MODAL'}
                    
                elif  event.type in {'RIGHTMOUSE', 'ESC'} and event.value == 'PRESS' and self.hot_key:
                    self.cut_line_widget.cancel_transform()
                    self.selected.cut_object(context, self.original_form, self.bme)
                    self.selected.simplify_cross(self.selected_path.ring_segments)
                    self.selected.update_com()
                    
                    self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                    self.selected_path.update_visibility(context, self.original_form)
                    
                return {'RUNNING_MODAL'}
            
            
                
                
            return{'RUNNING_MODAL'}
        
        if self.mode == 'GUIDE':
            
            if self.modal_state == 'WAITING':
                #NAVIGATION KEYS
                if (event.type in {'MIDDLEMOUSE', 
                                    'NUMPAD_2', 
                                    'NUMPAD_4', 
                                    'NUMPAD_6',
                                    'NUMPAD_8', 
                                    'NUMPAD_1', 
                                    'NUMPAD_3', 
                                    'NUMPAD_5', 
                                    'NUMPAD_7',
                                    'NUMPAD_9'} and event.value == 'PRESS'):
                    
                    self.modal_state = 'NAVIGATING'
                    self.post_update = True
                    context.area.header_text_set(text = 'NAVIGATING')

                    return {'PASS_THROUGH'}
                
                #ZOOM KEYS
                elif (event.type in  {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and not 
                        (event.ctrl or event.shift)):
                    
                    self.post_update = True
                    context.area.header_text_set(text = self.mode + ': ZOOM')
                    return{'PASS_THROUGH'}
                
                elif event.type == 'TAB' and event.value == 'PRESS':
                    self.mode = 'LOOP'
                    context.area.header_text_set(text = self.mode +':  WAITING')
                    return {'RUNNING_MODAL'}
                
                elif event.type == 'C' and event.value == 'PRESS':
                    #center cursor
                    bpy.ops.view3d.view_center_cursor()
                    return {'RUNNING_MODAL'}
                    
                elif event.type == 'N' and event.value == 'PRESS':
                    self.force_new = self.force_new != True
                    #self.selected_path = None
                    #self.snap = None
                    context.area.header_text_set(text = self.mode +': FORCE NEW: ' + str(self.force_new))
                    return {'RUNNING_MODAL'}
                
                
                elif event.type == 'MOUSEMOVE':
                    
                    self.hover_guide_mode(context, settings, event)
                    
                    return {'RUNNING_MODAL'}

                    
                elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                    if self.hover_target and self.hover_target.desc == 'CUT SERIES':
                        self.hover_target.do_select(settings)
                        self.selected_path = self.hover_target
                        
                        for path in self.cut_paths:
                            if path != self.hover_target:
                                path.deselect(settings)
                    else:
                        self.modal_state = 'DRAWING'
                        context.area.header_text_set(text = self.mode +': DRAWING')
                    
                    return {'RUNNING_MODAL'}    
                
                if self.selected_path:

                    if event.type in {'X', 'DEL'} and event.value == 'PRESS':
                        #delete the path
                        print('DELETD!')
                        self.cut_paths.remove(self.selected_path)
                        self.selected_path = None
                        self.modal_state = 'WAITING'
                        context.area.header_text_set(text = self.mode +': WAITING')
                        return {'RUNNING_MODAL'}
                    
                    elif (event.type in {'LEFT_ARROW', 'RIGHT_ARROW'} and 
                          event.value == 'PRESS'):
                        
                        self.guide_arrow_shift(context, event)
                          
                        #shift entire segment
                        context.area.header_text_set(text = self.mode +': Shift ')
                        return {'RUNNING_MODAL'}
                        
                    elif ((event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.ctrl) or
                          (event.type in {'NUMPAD_PLUS','NUMPAD_MINUS'} and event.value == 'PRESS')):
                          
                        #if not selected_path.lock:
                        #TODO: path.locked
                        #TODO:  dont recalc the path when no change happens
                        if event.type in {'WHEELUPMOUSE','NUMPAD_PLUS'}:
                            if not self.selected_path.seg_lock:
                                self.selected_path.segments += 1
                        elif event.type in {'WHEELDOWNMOUSE', 'NUMPAD_MINUS'} and self.selected_path.segments > 3:
                            if not self.selected_path.seg_lock:
                                
                                self.selected_path.segments -= 1
                    
                        if not self.selected_path.seg_lock:
                            self.selected_path.create_cut_nodes(context)
                            self.selected_path.snap_to_object(self.original_form, raw = False, world = False, cuts = True)
                            self.selected_path.cuts_on_path(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            self.selected_path.update_visibility(context, self.original_form)
                            self.selected_path.backbone_from_cuts(context, self.original_form, self.bme)
                            #path.segments
                            #distribute cut points
                            #make new cuts
                            #alignment
                            #etc
                        #else:
                            #let the user know the path is locked
                            #header message set
                            context.area.header_text_set(text = self.mode +': PATH SEGMENTS')
                            
                        else:
                            context.area.header_text_set(text = self.mode +': Path is locked, cannot adjuste # of segments')
                        return {'RUNNING_MODAL'}
                   
                    elif event.type == 'S' and event.value == 'PRESS':

                        if event.shift:
                            #path.smooth_normals
                            self.selected_path.average_normals(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            context.area.header_text_set(text = 'SMOOTH NORMALS')
                            
                        elif event.ctrl:
                            #smooth CoM path
                            context.area.header_text_set(text = 'SMOOTH CoM')
                            self.selected_path.smooth_normals_com(context, self.original_form, self.bme, iterations = 2)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            
                        elif event.alt:
                            #path.interpolate_endpoints
                            self.selected_path.interpolate_endpoints(context, self.original_form, self.bme)
                            self.selected_path.connect_cuts_to_make_mesh(self.original_form)
                            context.area.header_text_set(text = 'INTERPOLATE ENDPOINTS')
                            
                        else:
                            half = math.floor(self.selected_path.segments/2)
                            
                            if math.fmod(self.selected_path.segments, 2):  #5 segments is 6 rings
                                loc = 0.5 * (self.selected_path.cuts[half].plane_com + self.selected_path.cuts[half+1].plane_com)
                            else:
                                loc = self.selected_path.cuts[half].plane_com
                            
                            context.scene.cursor_location = loc
                    
                        return{'RUNNING_MODAL'}
                        
            if self.modal_state == 'DRAWING':
                
                if event.type == 'MOUSEMOVE':
                    action = 'GUIDE MODE: Drawing'
                    x = str(event.mouse_region_x)
                    y = str(event.mouse_region_y)
                    message = action + ": X: " +  x + '  Y:  ' +  y
                    context.area.header_text_set(text = message)
                    
                    #record screen drawing
                    self.draw_cache.append((event.mouse_region_x,event.mouse_region_y))   
                    
                    return {'RUNNING_MODAL'}
                    
                if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                    if len(self.draw_cache) > 10:
                    
                        
                        for path in self.cut_paths:
                            path.deselect(settings)
                            
                        self.selected_path  = self.new_path_from_draw(context, settings)
                        self.selected = self.selected_path.cuts[-1]
                        
                        self.drag = False #TODO: is self.drag still needed?
                        self.force_new = False
                    
                    self.draw_cache = []
                    
                    
                    self.modal_state = 'WAITING'
                    context.area.header_text_set(text = 'GUIDE MODE: WAITING')
                    return{'RUNNING_MODAL'}
                
                
            return{'RUNNING_MODAL'}
            
    def write_to_cache(self,tool_type):
        global contour_cache
        
        if tool_type in contour_cache:
            del contour_cache[tool_type]
            
        if len(self.valid_cuts):
            normals = [cut.plane_no for cut in self.valid_cuts]
            x_vecs = [cut.vec_x for cut in self.valid_cuts]
            y_vecs = [cut.vec_y for cut in self.valid_cuts]
            plane_pts = [cut.plane_pt for cut in self.valid_cuts]
            seeds = [cut.seed_face_index for cut in self.valid_cuts]
            fine_shifts = [cut.shift for cut in self.valid_cuts]
            int_shifts = [cut.int_shift for cut in self.valid_cuts]
            verts = [cut.verts for cut in self.valid_cuts]
            verts_simple = [cut.verts_simple for cut in self.valid_cuts]
            
            
            #todo, make this a little betetr
            validate = [self.original_form.name, len(self.bme.faces), len(self.bme.verts), len(self.original_form.modifiers)]
            contour_cache[tool_type] = {'validate': validate,
                                        'normals': normals,
                                        'x_vecs':x_vecs,
                                        'y_vecs':y_vecs,
                                        'plane_pts':plane_pts,
                                        'seeds':seeds,
                                        'shifts':fine_shifts,
                                        'int_shifts':int_shifts,
                                        'segments': self.segments}#,
   
    def load_from_cache(self,context, tool_type,clip):
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        if tool_type not in contour_cache:
            return None
        else:
            data = contour_cache[tool_type]
            if [self.original_form.name, len(self.bme.faces), len(self.bme.verts), len(self.original_form.modifiers)] == data['validate']:
                normals = data['normals']
                x_vecs = data['x_vecs']
                y_vecs = data['y_vecs']
                plane_pts = data['plane_pts']
                #verts = data['verts']
                #verts_simple = data['verts_simple']
                seeds = data['seeds']
                shifts = data['shifts']
                int_shifts = data['int_shifts']
                segments = data['segments']
                
                
                #settings and things
                (settings.geom_rgb[0],settings.geom_rgb[1],settings.geom_rgb[2],1)
                gc = settings.geom_rgb
                lc = settings.stroke_rgb
                vc = settings.vert_rgb
                hc = settings.handle_rgb
                
                g_color = (gc[0],gc[1],gc[2],1)
                l_color = (lc[0],lc[1],lc[2],1)
                v_color = (vc[0],vc[1],vc[2],1)
                h_color = (hc[0],hc[1],hc[2],1)
        
                for i, plane_no in enumerate(normals):
                    if i > (len(normals) - 1- clip): continue
                    cut = ContourCutLine(0, 0, line_width = settings.line_thick, stroke_color = l_color, handle_color = h_color, geom_color = g_color, vert_color = v_color)
                    cut.plane_no = plane_no
                    cut.seed_face_index = seeds[i]
                    cut.vec_x = x_vecs[i]
                    cut.vec_y = y_vecs[i]
                    cut.plane_pt = plane_pts[i]
                    cut.shift = shifts[i]
                    cut.int_shift = int_shifts[i]
                    
                    cut.cut_object(context, self.original_form, self.bme)
                    cut.simplify_cross(segments)
                    
                    cut.update_com()
                    #cut.verts = verts[i]
                    #cut.verts_simple = verts_simple[i]     
                     
                    cut.deselect(settings) 
                    self.cut_lines.append(cut)
                    self.valid_cuts.append(cut)
                    self.align_cut(cut, mode='DIRECTION', fine_grain=False)
                    cut.shift = shifts[i]
                    cut.int_shift = int_shifts[i]
                    cut.simplify_cross(segments)
                    
                    cut.update_screen_coords(context)
                    
                self.connect_valid_cuts_to_make_mesh()
                        
    def create_undo_entry(self, action, cut):
    
        available_actions = {'CREATE','DELETE','TRANSFORM','SHIFT','ALIGN','SEGMENT'}
        if action not in available_actions:
            return None
        
        print('undo push %s' % action)
        #it's a dictionary
        undo = {}
        
        #record what kind of action it is
        undo['action'] = action
        #how many segments are
        undo['segments'] = self.segments
        
        #these are the props we will record about a cut
        cut_props = ['plane_com',
                     'plane_no',
                     'plane_pt',
                     'seed_face_index',
                     'shift',
                     'int_shift',
                     'vec_x',
                     'vec_y']
    
        #record the relevant props
        if cut:
            for prop in cut_props:
                undo[prop] = getattr(cut, prop) 
            
        if action in {'DELETE'}:
            #Special case, we will actually keep the cut in cache
            #to put it back later
            undo['cut'] = cut
            
        elif action == 'SEGMENT':
            undo['cut'] = None
        else:
            undo['cut'] = self.cut_lines.index(cut)
            
        contour_undo_cache.append(undo)
        print('the undo cache grew, but this size may be irrelevant because of containers etc')
        print(sys.getsizeof(contour_undo_cache))
    
    def undo_action(self,context):
        
        if len(contour_undo_cache) > 0:
            undo = contour_undo_cache.pop()
            
            action = undo['action']
            
            #this may be an actual cut line
            #or it may be an index?
            
            #these are the props we will recorded about a cut
            cut_props = ['plane_com',
                         'plane_no',
                         'plane_pt',
                         'seed_face_index',
                         'shift',
                         'int_shift',
                         'vec_x',
                         'vec_y']
            
            if action == 'CREATE':
                cut = self.cut_lines[undo['cut']]
                if cut in self.valid_cuts:
                    self.valid_cuts.remove(cut)
                if cut in self.cut_lines:
                    self.cut_lines.remove(cut)
                    
                self.connect_valid_cuts_to_make_mesh()
                    
            elif action == 'DELETE':
                #in this circumstance...it's actually a cut
                cut = undo['cut']
                self.cut_lines.append(cut)
                self.sort_cuts()
                self.connect_valid_cuts_to_make_mesh()
                
                
            elif action in {'TRANSFORM', 'SHIFT','ALIGN'}:
                cut = self.cut_lines[undo['cut']]
                for prop in cut_props:
                    print(prop)
                    setattr(cut, prop, undo[prop])
                    
                    
                cut.cut_object(context, self.original_form, self.bme)
                cut.simplify_cross(self.segments)
                self.align_cut(cut, mode = 'DIRECTION', fine_grain = False)
                cut.update_screen_coords(context)
                self.connect_valid_cuts_to_make_mesh()
                
            elif action == 'SEGMENT':
                old_segments = self.segments
                self.segments = undo['segments']
                ratio = self.segments/old_segments
                for cut_line in self.cut_lines:
                    new_bulk_shift = round((cut_line.int_shift + cut_line.shift) * ratio)
                    new_fine_shift = ratio * (cut_line.shift + cut_line.int_shift) - new_bulk_shift
                                
                    cut_line.int_shift = new_bulk_shift
                    cut_line.shift = new_fine_shift
                                
                    cut_line.simplify_cross(self.segments)
                    cut_line.update_screen_coords(context)
                
                self.connect_valid_cuts_to_make_mesh()
                    

  
    def invoke(self, context, event):
        #TODO Settings harmon CODE REVIEW
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        self.valid_cut_inds = []
        self.existing_loops = []
        #clear the undo cache
        contour_undo_cache = []
        
        #TODO Settings harmon CODE REVIEW
        self.settings = settings
        
        #default verts in a loop (spans)
        self.segments = settings.vertex_count
        #default number of loops in a segment
        self.guide_cuts = settings.cut_count
        
        #if edit mode
        if context.mode == 'EDIT_MESH':
            
            #retopo mesh is the active object
            self.destination_ob = context.object  #TODO:  Clarify destination_ob as retopo_on consistent with design doc
            
            #get the destination mesh data
            self.dest_me = self.destination_ob.data
            
            #we will build this bmesh using from editmesh
            self.dest_bme = bmesh.from_edit_mesh(self.dest_me)
            
            #the selected object will be the original form
            #or we wil pull the mesh cache
            target = [ob for ob in context.selected_objects if ob.name != context.object.name][0]
            
            #this is a simple set of recorded properties meant to help detect
            #if the mesh we are using is the same as the one in the cache.
            validation = object_validation(target)
            
            if 'valid' in contour_mesh_cache and contour_mesh_cache['valid'] == validation:
                use_cache = True
                print('willing and able to use the cache!')
            
            else:
                use_cache = False  #later, we will double check for ngons and things
                clear_mesh_cache()
                self.original_form = target
                
            
            #count and collect the selected edges if any
            ed_inds = [ed.index for ed in self.dest_bme.edges if ed.select]
            
            self.existing_loops = []
            if len(ed_inds):
                vert_loops = contour_utilities.edge_loops_from_bmedges(self.dest_bme, ed_inds)
                
                print('there are %i edge loops selected' % len(vert_loops))
                for loop in vert_loops:
                    
                    if loop[-1] != loop[0] and len(list(set(loop))) != len(loop):
                        self.report({'WARNING'},'Edge loop selection has extra parts!  Excluding this loop')
                        
                    else:
                        lverts = [self.dest_bme.verts[i] for i in loop]
                        
                        self.existing_loops.append(ExistingVertList(lverts, 
                                                     loop, 
                                                     self.destination_ob.matrix_world,
                                                     key_type = 'INDS'))
                

        elif context.mode == 'OBJECT':
            
            #make the irrelevant variables None
            self.sel_edges = None
            self.sel_verts = None
            self.existing_cut = None
            
            #the active object will be the target
            target = context.object
            
            validation = object_validation(target)
            
            if 'valid' in contour_mesh_cache and contour_mesh_cache['valid'] == validation:
                use_cache = True
            
            else:
                use_cache = False
                self.original_form  = target #TODO:  Clarify original_form as reference_form consistent with design doc
            
            #no temp bmesh needed in object mode
            #we will create a new obeject
            self.tmp_bme = None
            
            #new blank mesh data
            self.dest_me = bpy.data.meshes.new(target.name + "_recontour")
            
            #new object to hold mesh data
            self.destination_ob = bpy.data.objects.new(target.name + "_recontour",self.dest_me) #this is an empty currently
            self.destination_ob.matrix_world = target.matrix_world
            self.destination_ob.update_tag()
            
            #destination bmesh to operate on
            self.dest_bme = bmesh.new()
            self.dest_bme.from_mesh(self.dest_me)
            

        
        #get the info about the original form
        #and convert it to a bmesh for fast connectivity info
        #or load the previous bme to save even more time
        
        
        
        if use_cache:
            start = time.time()
            print('the cache is valid for use!')
            
            self.bme = contour_mesh_cache['bme']
            print('loaded old bme in %f' % (time.time() - start))
            
            start = time.time()
            
            self.tmp_ob = contour_mesh_cache['tmp']
            print('loaded old tmp ob in %f' % (time.time() - start))
            
            if self.tmp_ob:
                self.original_form = self.tmp_ob
            else:
                self.original_form = target
              
        else:
    
            start = time.time()
            
            #clear any old saved data
            clear_mesh_cache()
            
            
            me = self.original_form.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            me.update()
            
            self.bme = bmesh.new()
            self.bme.from_mesh(me)
             
            #check for ngons, and if there are any...triangulate just the ngons
            #this mainly stems from the obj.ray_cast function returning triangulate
            #results and that it makes my cross section method easier.
            ngons = []
            for f in self.bme.faces:
                if len(f.verts) > 4:
                    ngons.append(f)
            if len(ngons) or len(self.original_form.modifiers) > 0:
                print('Ngons or modifiers detected this is a real hassle just so you know')
                
                if len(ngons):
                    new_geom = bmesh.ops.triangulate(self.bme, faces = ngons, use_beauty = True)
                    new_faces = new_geom['faces']
                    
                    
                new_me = bpy.data.meshes.new('tmp_recontour_mesh')
                self.bme.to_mesh(new_me)
                new_me.update()
                
                
                self.tmp_ob = bpy.data.objects.new('ContourTMP', new_me)
                
                
                #I think this is needed to generate the data for raycasting
                #there may be some other way to update the object
                context.scene.objects.link(self.tmp_ob)
                self.tmp_ob.update_tag()
                context.scene.update() #this will slow things down
                context.scene.objects.unlink(self.tmp_ob)
                self.tmp_ob.matrix_world = self.original_form.matrix_world
                
                
                ###THIS IS A HUGELY IMPORTANT THING TO NOTICE!###
                #so maybe I need to make it more apparent or write it differnetly#
                #We are using a temporary duplicate to handle ray casting
                #and triangulation
                self.original_form = self.tmp_ob
                
            else:
                self.tmp_ob = None
            
            
            #store this stuff for next time.  We will most likely use it again
            #keep in mind, in some instances, tmp_ob is self.original orm
            #where as in others is it unique.  We want to use "target" here to
            #record validation because that is the the active or selected object
            #which is visible in the scene with a unique name.
            write_mesh_cache(target, self.tmp_ob, self.bme)
            print('derived new bme and any triangulations in %f' % (time.time() - start))

        message = "Segments: %i" % self.segments
        context.area.header_text_set(text = message)
            
        #here is where we will cache verts edges and faces
        #unti lthe user confirms and we output a real mesh.
        self.verts = []
        self.edges = []
        self.faces = []
            
       
        if settings.use_x_ray:
            self.orig_x_ray = self.destination_ob.show_x_ray
            self.destination_ob.show_x_ray = True
            
            
        ####MODE, UI, DRAWING, and MODAL variables###
        self.mode = 'LOOP'
        #'LOOP' or 'GUIDE'
        
        self.modal_state = 'WAITING'
        
        #Loop and Guide Mode
        #'WAITING'
        #'NAVIGATING'
        
        #Loop Mode
        #'WIDGET TRANSFORM'
        #'CUTTING'
        #'HOTKEY TRANSFORM'
        
        #Guide Mode
        #'DRAWING'
        
        
        #does the user want to extend an existing cut or make a new segment
        self.force_new = False
        
        #is the mouse clicked and held down
        self.drag = False
        self.navigating = False
        self.post_update = False
        
        #what is the user dragging..a cutline, a handle etc
        self.drag_target = None
        
        #potential item for snapping in 
        self.snap = []
        self.snap_circle = []
        self.snap_color = (1,0,0,1)
        
        #what is the mouse over top of currently
        self.hover_target = None
        #keep track of selected cut_line and path
        self.selected = None   #TODO: Change this to selected_loop
        self.selected_path = None   #TODO: change this to selected_segment
        
        
        self.cut_line_widget = None  #An object of Class "CutLineManipulator" or None
        self.widget_interaction = False  #Being in the state of interacting with a widget o
        self.hot_key = None  #Keep track of which hotkey was pressed
        self.draw = False  #Being in the state of drawing a guide stroke
        
        
        #This is a cache for any cut line whose connectivity
        #has not been established.
        self.cut_lines = []
        
        #a list of all the cut paths (segments)
        self.cut_paths = []
        #a list to store screen coords when drawing
        self.draw_cache = []
        
    
        self.header_message = 'LMB: Select Stroke, RMB / X: Delete Sroke, , G: Translate, R: Rotate, A / Ctrl+A / Shift+A: Align, S: Cursor to Stroke, C: View to Cursor'
        context.area.header_text_set(self.header_message)
        if settings.recover:
            print('loading cache!')
            print(contour_cache['CUT_LINES'])
            self.load_from_cache(context, 'CUT_LINES', settings.recover_clip)
        #add in the draw callback and modal method
        self._handle = bpy.types.SpaceView3D.draw_handler_add(retopo_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}


def poly_sketch_draw_callback(self,context):
    
    if (self.post_update or self.navigating) and context.space_data.use_occlude_geometry:
        for line in self.sketch_lines:
            line.update_visibility(context, self.original_form)
            
        self.post_update = False
                        
    if len(self.draw_cache):
        contour_utilities.draw_polyline_from_points(context, self.draw_cache, (1,.5,1,.8), 2, "GL_LINE_SMOOTH")
    
    
    if len(self.sketch_intersections):
        contour_utilities.draw_3d_points(context, self.sketch_intersections, (0,0, 1,1), 5)
        
    if len(self.sketch_lines):    
        for line in self.sketch_lines:
            line.draw(context)
            
    if len(self.mouse_circle):
        contour_utilities.draw_polyline_from_points(context, self.mouse_circle, (.7,.1,.8,.8), 2, "GL_LINE_SMOOTH")

class CGCOOKIE_OT_retopo_poly_sketch(bpy.types.Operator):
    '''Sketch Toplogy on Forms with Contour Strokes'''
    bl_idname = "cgcookie.retopo_poly_sketch"
    bl_label = "Contour Poly Sketch"    
    
    @classmethod
    def poll(cls,context):
        if context.mode not in {'EDIT_MESH','OBJECT'}:
            return False
        
        if context.active_object:
            if context.mode == 'EDIT_MESH':
                if len(context.selected_objects) > 1:
                    return True
                else:
                    return False
            else:
                return context.object.type == 'MESH'
        else:
            return False
        
    def modal(self, context, event):
        context.area.tag_redraw()
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        
        
        
        if event.type == 'K' and self.selected and self.selected.desc == 'SKETCH_LINE':
            if event.value == 'PRESS':
                self.selected.cut_by_endpoints(self.original_form, self.bme)
            
            return {'RUNNING_MODAL'}
            
        if event.type == 'R':
            #for line in self.sketch_lines:
                #if len(line.poly_nodes) <= 2:
                    #print('getting rid of one')
                    #self.sketch_lines.remove(line) 
                            
            print('################')
            print('               ')
            print('PROGRESS REPORT')
            print('               ')
            
            for i, sketch in enumerate(self.sketch_lines):
                print('this is the %i segment' % i)
                print('world path is %i long: ' % len(sketch.world_path))
                print('raw world is %i long: ' % len(sketch.raw_world))
                print('poly nodes is %i long: ' % len(sketch.poly_nodes))
                print('there are %i segments: ' % sketch.segments)
                print('    ')
        
        
        if event.type in {'WHEELDOWNMOUSE','WHEELUPMOUSE','NUMPAD_PLUS','NUMPAD_MINUS'}:
            
            if (event.type == 'WHEELUPMOUSE' and event.ctrl) or (event.type == 'NUMPAD_PLUS' and event.value == 'PRESS'):
                
                if self.selected and self.selected.desc == 'SKETCH_LINE' and not self.draw:
                    self.selected.segments += 1
                    self.selected.create_vert_nodes(context, mode = 'SEGMENTS')
                    self.selected.generate_quads(self.original_form)
                    message = "%s: Set segments to %i" % (event.type, self.selected.segments)
                    context.area.header_text_set(text = message)
                
                    #self.connect_valid_cuts_to_make_mesh()
                return {'RUNNING_MODAL'}
            
            elif (event.type == 'WHEELDOWNMOUSE' and event.ctrl) or (event.type == 'NUMPAD_MINUS' and event.value == 'PRESS'):
                
                if self.selected and self.selected.desc == 'SKETCH_LINE' and not self.draw:
                    if self.selected.segments > 1:
                        self.selected.segments -= 1
                        self.selected.create_vert_nodes(context, mode = 'SEGMENTS')
                        self.selected.generate_quads(self.original_form)
                        message = "%s: Set segments to %i" % (event.type, self.selected.segments)
                        context.area.header_text_set(text = message)
                        
                return {'RUNNING_MODAL'}
            
            elif (event.type == 'WHEELUPMOUSE' and event.alt) or (event.type == 'UP_ARROW' and event.value == 'PRESS'):
                
                if self.selected and self.selected.desc == 'SKETCH_LINE' and not self.draw:
                    
                    if event.shift:
                        self.selected.quad_width += .05 * self.original_form.dimensions.length * 1/settings.density_factor
                    
                    else:
                        self.selected.quad_width += .1 * self.original_form.dimensions.length * 1/settings.density_factor
                   
                    message = "%s: Set width to %f" % (event.type, round(self.selected.quad_width,3))
                    context.area.header_text_set(text = message)
                    self.selected.generate_quads(self.original_form)
                    #message = "%s: Set segments to %i" % (event.type, self.selected.segments)
                    #context.area.header_text_set(text = message)
                
                    #self.connect_valid_cuts_to_make_mesh()
                return {'RUNNING_MODAL'}
            
            elif (event.type == 'WHEELDOWNMOUSE' and event.alt) or (event.type == 'DOWN_ARROW' and event.value == 'PRESS'):
                
                if self.selected and self.selected.desc == 'SKETCH_LINE' and not self.draw:
                    if event.shift:
                        self.selected.quad_width -= .05 * self.original_form.dimensions.length * 1/settings.density_factor
                    
                    else:
                        self.selected.quad_width -= .1 * self.original_form.dimensions.length * 1/settings.density_factor
                    
                    if self.selected.quad_width < 0:
                        self.selected.quad_width = .01 * self.original_form.dimensions.length * 1/settings.density_factor
                        
                    message = "%s: Set width to %f" % (event.type, round(self.selected.quad_width,3))
                    context.area.header_text_set(text = message)
                    self.selected.generate_quads(self.original_form)
                return {'RUNNING_MODAL'}
            
                
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'MIDDLEMOUSE', 'NUMPAD_2', 'NUMPAD_4', 'NUMPAD_6', 'NUMPAD_8', 'NUMPAD_1', 'NUMPAD_3', 'NUMPAD_5', 'NUMPAD_7', 'NUMPAD_9'}:
            
            for line in self.sketch_lines:
                line.update_visibility(context, self.original_form)
            
            if event.value == 'PRESS':
                self.navigating = True
                
            else:
                self.navigating = False
                
            self.post_update = True
            return {'PASS_THROUGH'}
            
            
        elif event.type == 'D':
            
            #toggle drawing
            if event.value == 'PRESS':
                #toggle the draw on press
                self.draw = self.draw == False
            
            
            if self.draw:
                message = "Stick draw on"
                
            else:
                message = "Experimental poly_sketch tap 'D' to draw"
            context.area.header_text_set(text = message)    
            #else:
                #self.draw = False
                #self.draw_cache = []
                
            return {'RUNNING_MODAL'}
        
        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if self.hover_target:
                self.sketch_lines.remove(self.hover_target)
                self.hover_target = None
                self.selected = None
                
            return{'RUNNING_MODAL'}
                    
        elif event.type == 'MOUSEMOVE':
            #preview circle
            
            region = context.region  
            rv3d = context.space_data.region_3d
            vec = region_2d_to_vector_3d(region, rv3d, (event.mouse_region_x,event.mouse_region_y))
            loc = region_2d_to_location_3d(region, rv3d, (event.mouse_region_x,event.mouse_region_y), vec)
            if rv3d.is_perspective:
                #print('is perspe')
                a = loc - 3000*vec
                b = loc + 3000*vec
            else:
                #print('is not perspe')
                b = loc - 3000 * vec
                a = loc + 3000 * vec

            mx = self.original_form.matrix_world
            imx = mx.inverted()
            hit = self.original_form.ray_cast(imx*a, imx*b)
            if hit[2] != -1:
                print('raycast the mouse')
                world_v = mx * hit[0]
                r = self.original_form.dimensions.length * 1/settings.density_factor
                world_r = world_v + r * rv3d.view_rotation * Vector((1,0,0))
                screen_r = location_3d_to_region_2d(region,rv3d, world_r)
                screen_r_vec = Vector((event.mouse_region_x,event.mouse_region_y)) - screen_r
                radius = screen_r_vec.length/2
                self.mouse_circle = contour_utilities.simple_circle(event.mouse_region_x, event.mouse_region_y, radius, 20)
                self.mouse_circle.append(self.mouse_circle[0])
            else:
                print('didnt raycast the mouse')
                self.mouse_circle = []
                
                
            if self.drag and self.draw:
                
                self.draw_cache.append((event.mouse_region_x,event.mouse_region_y))
                
            if not self.drag and not self.draw:
                selection = []
                self.hover_target = None
                for sketch in self.sketch_lines:
                    act = sketch.active_element(context, event.mouse_region_x, event.mouse_region_y)
                    if act and act.desc == 'SKETCH_LINE':
                        self.hover_target = act
                        self.hover_target.color2 = (settings.sketch_color5[0], settings.sketch_color5[1],settings.sketch_color5[2],1)
                        
                    elif not act and not sketch.select:
                        sketch.color2 = (settings.sketch_color2[0], settings.sketch_color2[1],settings.sketch_color2[2],1)

                        

                    
            
            return {'RUNNING_MODAL'}
                    
                    
        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                
                
                
                if not self.draw and self.hover_target:
                    for sketch in self.sketch_lines:
                        sketch.select = False
                        sketch.color2 = (settings.sketch_color2[0], settings.sketch_color2[1],settings.sketch_color2[2],1)
                    
                    #tell the operator who is selected    
                    self.selected = self.hover_target
                    #tell the line that it's selected
                    self.selected.select = True
                    #color it appropriately
                    self.selected.color2 = (settings.sketch_color5[0], settings.sketch_color5[1],settings.sketch_color5[2],1)
                

                else:
                    self.drag = True
                
                
            else:
                if self.draw:
                    if len(self.draw_cache) > 10:
                        #new sketch
                        
                        sketch = PolySkecthLine(context, self.draw_cache,
                                                cull_factor = settings.cull_factor, 
                                                smooth_factor = settings.smooth_factor,
                                                feature_factor = settings.feature_factor)
                        
                        #cast onto object
                        sketch.ray_cast_path(context, self.original_form)
                        
                        #find knots later
                        #sketch.find_knots()
                        
                        #TODO:  inefficient but needed.
                        #snapping requires a smoothed path
                        #to check parallel ness
                        #consider other test
                        sketch.smooth_path(context, ob = self.original_form)
                        #asses the new line's relationship to all the others
                        for line in self.sketch_lines:
                            sketch.snap_self_to_other_line(line)
                            
                        sketch.process_relations(context, self.original_form, self.sketch_lines)
                        
                        #start with just the new stroke
                        all_new = [sketch]
                        #all the existing non intersecting strokes are self.sketch_lines
                        
                        if len(self.sketch_lines):
                            new_strokes = True
                            tests = 0
                            while new_strokes != [] and tests < 100:
                                tests += 1
                                if tests > 99:
                                    print('numbered out...too many tests')
                                
                                for sketch in all_new:
                                    
                                    break_out = False
                                    for line in self.sketch_lines:
                                        
                                        new_strokes = self.intersect_strokes(context, sketch, line)
                                        if new_strokes != []:
                                            print('removing the old from the existing')
                                            self.sketch_lines.remove(line)
                                            print('removing the original from the new set')
                                            all_new.remove(sketch)
                                            print('adding %i new strokes back to the new set' % len(new_strokes))
                                            all_new.extend(new_strokes)
                                            break_out = True
                                            break
                                    if break_out:
                                        break
                                    
                        
                        for line in all_new:
                            #the target density will carry over in the new lines
                            #hack for now
                            if len(line.poly_nodes) == 0:
                                line.create_vert_nodes(context, mode = 'QUAD_SIZE')
                            
                            if len(line.extrudes_d) == 0:
                                line.generate_quads(self.original_form)
                            
                            
                            
                        for line in all_new:
                            if len(line.poly_nodes) < 2:
                                print('cleaning a small line')
                                all_new.remove(line)
                                
                        self.sketch_lines.extend(all_new)  
                        
                        for sketch in self.sketch_lines:
                            sketch.select = False
                            
                        self.selected = None
                        
                        
                                
                        #other_sketches = sketch.intersect_other_paths(context, self.sketch_lines, separate_other = True)
                        
                        #.create_vert_nodes()
                        #sketch.generate_quads(self.original_form,1)
                        
                        #self.sketch_lines.append(sketch)
                        #if len(other_sketches):
                            #for line in other_sketches:
                                #line.create_vert_nodes()
                                
                                
                            #self.sketch_lines.extend(other_sketches)
                        
                        self.draw_cache = []
                        
                    #for line in self.sketch_lines:
                        #if len(line.poly_nodes) <= 2:
                            #print('getting rid of one')
                            #self.sketch_lines.remove(line)             
                        
                
                    else:
                        #draw cache is too short, toss it.
                        self.draw_cache = []
                self.drag = False
                
            return {'RUNNING_MODAL'}
        
        elif event.type == 'ESC':
            contour_utilities.callback_cleanup(self,context)
            context.area.header_text_set()
            return {'CANCELLED'}
            
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if context.mode == 'EDIT_MESH':
                back_to_edit = True
            else:
                back_to_edit = False
                
            bm = self.dest_bme
                
            #the world_matrix of the orignal form
            orig_mx = self.original_form.matrix_world
    
            #the world matrix of the destination (retopo) mesh
            reto_mx = self.destination_ob.matrix_world
            reto_imx = reto_mx.inverted()
            
            #make list of bmverts
            
            for line in self.sketch_lines: 
                bmverts = []
                    
                for i, vert in enumerate(line.extrudes_u):
                    new_vert = bm.verts.new(tuple(reto_imx * vert))
                    bmverts.append(new_vert)
                    
                for i, vert in enumerate(line.extrudes_d):
                    new_vert = bm.verts.new(tuple(reto_imx * vert))
                    bmverts.append(new_vert)
                

            
                # Initialize the index values of this sequence
                self.dest_bme.verts.index_update()
                
                #gather a few
                n_faces = len(line.extrudes_u) - 1

                #this will leave room later for t junctions etc
                total_faces = []
                for j in range(0,n_faces): #there are only 2 rings...but i left it here for readability
                    
                    ind0 = j
                    ind1 = j + 1
                    ind2 = j + 1 + n_faces + 1
                    ind3 = j +n_faces + 1
                    total_faces.append((ind0,ind1,ind2,ind3))
            
                bmfaces = []
                for face in total_faces:

                    #actual BMVerts not indices I think?
                    new_face = tuple([bmverts[i] for i in face])
                    bmfaces.append(bm.faces.new(new_face))
            
            
            # Finish up, write the modified bmesh back to the mesh
            
            #if editmode...we have to do it this way
            if context.mode == 'EDIT_MESH':
                bmesh.update_edit_mesh(self.dest_me, tessface=False, destructive=True)
            
            #if object mode....we do it like this
            else:
                #write the data into the object
                bm.to_mesh(self.dest_me)
            
                #remember we created a new object
                #moving this to the invoke?
                context.scene.objects.link(self.destination_ob)
                
                self.destination_ob.select = True
                context.scene.objects.active = self.destination_ob
                
                if context.space_data.local_view:
                    view_loc = context.space_data.region_3d.view_location.copy()
                    view_rot = context.space_data.region_3d.view_rotation.copy()
                    view_dist = context.space_data.region_3d.view_distance
                    bpy.ops.view3d.localview()
                    bpy.ops.view3d.localview()
                    #context.space_data.region_3d.view_matrix = mx_copy
                    context.space_data.region_3d.view_location = view_loc
                    context.space_data.region_3d.view_rotation = view_rot
                    context.space_data.region_3d.view_distance = view_dist
                    context.space_data.region_3d.update()
                    
            self.destination_ob.update_tag()
            context.scene.update()
            
            context.area.header_text_set()
            contour_utilities.callback_cleanup(self,context)
            bm.free()

            return{'FINISHED'}
            
                
        else:
            return {'RUNNING_MODAL'}
    
    
    def intersect_strokes(self,context, stroke1, stroke2):
        settings = context.user_preferences.addons['cgc-retopology'].preferences

        return_strokes = []
        inter_dict1 = {}
        inter_dict2 = {}
        
        new_intersects, inds_1, inds_2 = contour_utilities.intersect_paths(stroke1.world_path, stroke2.world_path, cyclic1 = False, cyclic2 = False, threshold = .1)
        
        
        
        if new_intersects != []:
            for i, index in enumerate(inds_1):
                inter_dict1[index] = new_intersects[i]
            for i, index in enumerate(inds_2):
                inter_dict2[index] = new_intersects[i]
                    
            
            n1 = len(stroke1.raw_world) - 1
            n2 = len(stroke2.raw_world) - 1
            verts1 = stroke1.world_path.copy()
            verts2 = stroke2.world_path.copy()
            
            
            print('lengths')
            print(len(verts1))
            print(len(verts2))
            
            print('raw inds')
            print(inds_1)
            print(inds_2)
            
            if n1 not in inds_1:
                inds_1.append(n1+1)
                
            if n2 not in inds_2:
                inds_2.append(n2+1)
            
            print('dictionaries')    
            print(inter_dict1)
            print(inter_dict2)    
            #the first edge may have been intersected
            #meaning the first vert will be there already
            if 0 not in inds_1 and 0 not in inter_dict1:
                inds_1.insert(0,0)
                
            else:
                print('special damn case')
                
            if 0 not in inds_2 and 0 not in inter_dict2:
                inds_2.insert(0,0)
                
            else:
                print('special damn case')
                
            inds_1.sort()
            inds_2.sort()
            
            print('tagged ends')
            print(inds_1)
            print(inds_2)
            
            segments1 = []
            segments2 = []
            
            for i in range(0,len(inds_1) - 1):
                
                start_index = inds_1[i]
                end_index = inds_1[i+1]
                print('start index: %i stop_index: %i' % (start_index, end_index))
                
                if i > 0:
                    seg = verts1[start_index+1:end_index]
                
                else:
                    if start_index == 0 and 0 in inter_dict1:
                        seg_0 = [verts1[0], inter_dict1[0]]
                        seg = verts1[1:end_index]
                        seg.insert(0,inter_dict1[start_index])
                    
                        segments1.append(seg_0)
                        
                    else:
                        seg = verts1[start_index:end_index]
                    
                if start_index > 0:
                    seg.insert(0,inter_dict1[start_index])
                    
                if end_index < n1+1 and not (start_index == 0 and 0 in inter_dict1):
                    seg.append(inter_dict1[end_index])
                
                segments1.append(seg)
                
                
            tot_length = sum([len(seg) -1 for seg in segments1])
            print('length difference %i' % (tot_length - len(verts1)))
             
            for i in range(0,len(inds_2) - 1):
                
                start_index = inds_2[i]
                end_index = inds_2[i+1]
                print('start index: %i stop_index: %i' % (start_index, end_index))
                
                if i > 0:
                    seg = verts2[start_index+1:end_index]
                
                else:
                    if start_index == 0 and 0 in inter_dict2:
                        seg_0 = [verts2[0], inter_dict2[0]]
                        seg = verts2[1:end_index]
                        seg.insert(0,inter_dict2[0])
                        segments2.append(seg_0)
                    
                    else:
                        seg = verts2[start_index:end_index]
                        
                    
                    
                if start_index > 0:
                    seg.insert(0,inter_dict2[start_index])
                    
                if end_index < n2+1 and not (start_index == 0 and 0 in inter_dict2):
                    seg.append(inter_dict2[end_index])
                
                segments2.append(seg)
                
            
            for seg in segments1:
                #make a blank new stroke
                sketch = PolySkecthLine(context, [])
                sketch.raw_world = seg
                sketch.world_path = seg
                sketch.snap_to_object(self.original_form)
                sketch.quad_length = stroke1.quad_length
                sketch.quad_width = stroke1.quad_width
                #give them a highlight color for now
                sketch.color2 = (settings.sketch_color5[0], settings.sketch_color5[1],settings.sketch_color5[2],1)
                
                return_strokes.append(sketch)
                
            for seg in segments2:
                #make a new stroke
                sketch = PolySkecthLine(context, [])
                sketch.raw_world = seg
                sketch.world_path = seg
                sketch.quad_length = stroke2.quad_length
                sketch.quad_width = stroke2.quad_width
                return_strokes.append(sketch)
                
        return return_strokes        
        #build new stroke1 segments
        
        #build new stroke 2 segments
        
        
        
    def invoke(self, context, event):
        #HINT you are in the poly sketch code
        
        #TODO Settings harmon CODE REVIEW
        settings = context.user_preferences.addons['cgc-retopology'].preferences
        
        #TODO Settings harmon CODE REVIEW
        self.settings = settings
        
        #if edit mode
        if context.mode == 'EDIT_MESH':
            
            #the active object will be the retopo object
            #whose geometry we will be augmenting
            self.destination_ob = context.object
            
            #get the destination mesh data
            self.dest_me = self.destination_ob.data
            
            #we will build this bmesh using from editmesh
            self.dest_bme = bmesh.from_edit_mesh(self.dest_me)
            
            #the selected object will be the original form
            #or we wil pull the mesh cache
            target = [ob for ob in context.selected_objects if ob.name != context.object.name][0]
            
            validation = object_validation(target)
            if 'valid' in contour_mesh_cache and contour_mesh_cache['valid'] == validation:
                use_cache = True
                print('willing and able to use the cache!')
            
            else:
                use_cache = False  #later, we will double check for ngons and things
                clear_mesh_cache()
                self.original_form = target
                
            
            #count and collect the selected edges if any
            ed_inds = [ed.index for ed in self.dest_bme.edges if ed.select]
            
            if len(ed_inds):
                vert_loops = contour_utilities.edge_loops_from_bmedges(self.dest_bme, ed_inds)
                if len(vert_loops) > 1:
                    self.report({'ERROR'}, 'single edge loop must be selected')
                    #TODO: clean up things and free the bmesh
                    return {'CANCELLED'}
                
                else:
                    best_loop = vert_loops[0]
                    if best_loop[-1] != best_loop[0]: #typically this means not cyclcic unless there is a tail []_
                        if len(list(set(best_loop))) == len(best_loop): #verify no tail
                            self.sel_edges = [ed for ed in self.dest_bme.edges if ed.select]
                        
                        else:
                            self.report({'ERROR'}, 'Edge loop selection has extra parts')
                            #TODO: clean up things and free the bmesh
                            return {'CANCELLED'}
                    else:
                        self.sel_edges = [ed for ed in self.dest_bme.edges if ed.select]
            else:
                self.sel_edges = None
                
            if self.sel_edges and len(self.sel_edges):
                self.sel_verts = [vert for vert in self.dest_bme.verts if vert.select]
                
                #TODO...allow extnesion of selections
                #self.segments = len(self.sel_edges)
                #self.existing_cut = ExistingVertList(self.sel_verts, self.sel_edges,self.destination_ob.matrix_world)
            else:
                #self.existing_cut = None
                self.sel_verts = None
                self.segments = settings.vertex_count
            
        elif context.mode == 'OBJECT':
            
            #make the irrelevant variables None
            self.sel_edges = None
            self.sel_verts = None
            #self.existing_cut = None
            
            #the active object will be the target
            target = context.object
            
            validation = object_validation(target)
            
            if 'valid' in contour_mesh_cache and contour_mesh_cache['valid'] == validation:
                use_cache = True
            
            else:
                use_cache = False
                self.original_form  = target
            
            #no temp bmesh needed in object mode
            #we will create a new obeject
            self.tmp_bme = None
            
            #new blank mesh data
            self.dest_me = bpy.data.meshes.new(target.name + "_recontour")
            
            #new object to hold mesh data
            self.destination_ob = bpy.data.objects.new(target.name + "_recontour",self.dest_me) #this is an empty currently
            self.destination_ob.matrix_world = target.matrix_world
            self.destination_ob.update_tag()
            
            #destination bmesh to operate on
            self.dest_bme = bmesh.new()
            self.dest_bme.from_mesh(self.dest_me)
            
            #default segments (spans)
            self.segments = settings.vertex_count
        
        #get the info about the original form
        #and convert it to a bmesh for fast connectivity info
        #or load the previous bme to save even more time
        
        
        
        if use_cache:
            start = time.time()
            print('the cache is valid for use!')
            
            self.bme = contour_mesh_cache['bme']
            print('loaded old bme in %f' % (time.time() - start))
            
            start = time.time()
            
            self.tmp_ob = contour_mesh_cache['tmp']
            print('loaded old tmp ob in %f' % (time.time() - start))
            
            if self.tmp_ob:
                self.original_form = self.tmp_ob
            else:
                self.original_form = target
              
        else:
    
            start = time.time()
            
            #clear any old saved data
            clear_mesh_cache()
            
            me = self.original_form.to_mesh(scene=context.scene, apply_modifiers=True, settings='PREVIEW')
            self.bme = bmesh.new()
            self.bme.from_mesh(me)
             
            #check for ngons, and if there are any...triangulate just the ngons
            #this mainly stems from the obj.ray_cast function returning triangulate
            #results and that it makes my cross section method easier.
            ngons = []
            for f in self.bme.faces:
                if len(f.verts) > 4:
                    ngons.append(f)
            if len(ngons):
                print('Ngons detected, this is a real hassle just so you know')
                print('Ngons detected, this will probably double operator initial startup time')
                new_geom = bmesh.ops.triangulate(self.bme, faces = ngons, use_beauty = True)
                new_faces = new_geom['faces']
                new_me = bpy.data.meshes.new('tmp_recontour_mesh')
                self.bme.to_mesh(new_me)
                new_me.update()
                self.tmp_ob = bpy.data.objects.new('ContourTMP', new_me)
                
                
                #I think this is needed to generate the data for raycasting
                #there may be some other way to update the object
                context.scene.objects.link(self.tmp_ob)
                self.tmp_ob.update_tag()
                context.scene.update() #this will slow things down
                context.scene.objects.unlink(self.tmp_ob)
                self.tmp_ob.matrix_world = self.original_form.matrix_world
                
                
                ###THIS IS A HUGELY IMPORTANT THING TO NOTICE!###
                #so maybe I need to make it more apparent or write it differnetly#
                #We are using a temporary duplicate to handle ray casting
                #and triangulation
                self.original_form = self.tmp_ob
                
            else:
                self.tmp_ob = None
            
            
            #store this stuff for next time.  We will most likely use it again
            #keep in mind, in some instances, tmp_ob is self.original orm
            #where as in others is it unique.  We want to use "target" here to
            #record validation because that is the the active or selected object
            #which is visible in the scene with a unique name.
            write_mesh_cache(target, self.tmp_ob, self.bme)
            print('derived new bme and any triangulations in %f' % (time.time() - start))

        message = "Segments: %i" % self.segments
        context.area.header_text_set(text = message)
            
            
        #here is where we will cache verts edges and faces
        #unti lthe user confirms and we output a real mesh.
        self.verts = []
        self.edges = []
        self.faces = []
        
        #store points
        self.draw_cache = []
        self.post_update = False
        
        #mouse preview circle
        self.mouse_circle = []
        
        
        self.sketch_intersections = []
            
       
        if settings.use_x_ray:
            self.orig_x_ray = self.destination_ob.show_x_ray
            self.destination_ob.show_x_ray = True
            
        #is the mouse clicked and held down
        self.drag = False
        self.navigating = False
        self.draw = False
        
        #what is the user dragging..a cutline, a handle etc
        self.drag_target = None
        #what is the mouse over top of currently
        self.hover_target = None
        #keep track of selected cut_line (perhaps
        self.selected = None
        
        
        
        self.sketch_lines = []
        
        
        
        self.header_message = 'Experimental sketcying. D + LMB to draw'
        context.area.header_text_set(self.header_message)
        #if settings.recover:
            #print('loading cache!')
            #print(contour_cache['CUT_LINES'])
            #self.load_from_cache(context, 'CUT_LINES', settings.recover_clip)
        #add in the draw callback and modal method
        self._handle = bpy.types.SpaceView3D.draw_handler_add(poly_sketch_draw_callback, (self, context), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
# Used to store keymaps for addon
addon_keymaps = []


#resgistration
def register():
    bpy.utils.register_class(ContourToolsAddonPreferences)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_contour_panel)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_cache_clear)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_contour)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_poly_sketch)
    bpy.utils.register_class(CGCOOKIE_OT_retopo_contour_menu)

    # Create the addon hotkeys
    kc = bpy.context.window_manager.keyconfigs.addon
   
    # create the mode switch menu hotkey
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new('wm.call_menu', 'V', 'PRESS', ctrl=True, shift=True)
    kmi.properties.name = 'object.retopology_menu' 
    kmi.active = True
    addon_keymaps.append((km, kmi))
    

#unregistration
def unregister():
    clear_mesh_cache()
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_contour)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_cache_clear)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_contour_panel)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_contour_menu)
    bpy.utils.unregister_class(CGCOOKIE_OT_retopo_poly_sketch)
    bpy.utils.unregister_class(ContourToolsAddonPreferences)

    # Remove addon hotkeys
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
