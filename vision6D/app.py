from typing import List, Dict, Tuple
import pathlib
import logging
import numpy as np
import math
import trimesh
import functools
import json

import pyvista as pv
import matplotlib.pyplot as plt
import vision6D as vis
from scipy.spatial import distance_matrix

logger = logging.getLogger("vision6D")

class App:
    # The unit is mm
    def __init__(
            self,
            off_screen: bool,
            nocs_color: bool=False,
            point_clouds: bool=False,
            width: int=1920,
            height: int=1080,
            # use surgical microscope for medical device with view angle 1 degree
            cam_focal_length:int=5e+4,
            cam_viewup: Tuple=(0,-1,0),
            mirror_objects: bool=False
        ):
        
        self.off_screen = off_screen
        self.nocs_color = nocs_color
        self.point_clouds = point_clouds
        self.window_size = (int(width), int(height))
        self.mirror_objects = mirror_objects
        self.transformation_matrix = None
        self.reference = None

        # get the latlon color
        self.latlon = self.load_latitude_longitude(vis.config.CWD / "ossiclesCoordinateMapping.json")
        
        # initial the dictionaries
        self.mesh_actors = {}
        self.image_polydata = {}
        self.mesh_polydata = {}
        self.binded_meshes = {}
        self.initial_poses = {}
        
        # default opacity for image and surface
        self.set_image_opacity(1) # self.image_opacity = 0.35
        self.set_mesh_opacity(1) # self.surface_opacity = 1

        # Set up the camera
        self.camera = pv.Camera()
        self.cam_focal_length = cam_focal_length
        self.cam_viewup = cam_viewup
        self.cam_position = -(self.cam_focal_length/100) # -500mm
        self.set_camera_intrinsics(self.window_size[0], self.window_size[1], self.cam_focal_length)
        self.set_camera_extrinsics(self.cam_position, self.cam_viewup)
        
        # plot image and ossicles
        self.pv_plotter = pv.Plotter(window_size=[self.window_size[0], self.window_size[1]], off_screen=off_screen)

    def load_latitude_longitude(self, json_path):
        # get the latitude and longitude
        with open(json_path, "r") as f: data = json.load(f)
        
        latitude = np.array(data['latitude']).reshape((len(data['latitude'])), 1)
        longitude = np.array(data['longitude']).reshape((len(data['longitude'])), 1)
        placeholder = np.zeros((len(data['longitude']), 1))
        
        # set the latlon attribute
        latlon = np.hstack((latitude, longitude, placeholder))
        return latlon

    def load_image(self, image_source:np.ndarray, scale_factor:list=[0.01,0.01,1]):
        
        self.image_polydata['image'] = pv.UniformGrid(dimensions=(1920, 1080, 1), spacing=scale_factor, origin=(0.0, 0.0, 0.0))
        self.image_polydata['image'].point_data["values"] = image_source.reshape((1920*1080, 3)) # order = 'C
        self.image_polydata['image'] = self.image_polydata['image'].translate(-1 * np.array(self.image_polydata['image'].center), inplace=False)

        # Then add it to the plotter
        image = self.pv_plotter.add_mesh(self.image_polydata['image'], rgb=True, opacity=self.image_opacity, name='image')
        actor, _ = self.pv_plotter.add_actor(image, pickable=False, name="image")

        # Save actor for later
        self.image_actor = actor    

    def load_meshes(self, paths: Dict[str, (pathlib.Path or pv.PolyData)]):

        assert self.transformation_matrix is not None, "Need to set the transformation matrix first!"
                
        for mesh_name, mesh_source in paths.items():
            
            reference_name = mesh_name

            if isinstance(mesh_source, pathlib.WindowsPath) or isinstance(mesh_source, str):
                # Load the '.mesh' file
                # mesh_source.vertices = trimesh.sample.sample_surface(mesh_source, 10000000)[0]
                if '.mesh' in str(mesh_source): 
                    mesh_source = vis.utils.load_trimesh(mesh_source)
                    # Set vertices and faces attribute
                    self.set_mesh_info(mesh_name, mesh_source)
                    if self.nocs_color: colors = vis.utils.color_mesh(mesh_source.vertices)
                    else:
                        if mesh_name == 'ossicles': colors = self.latlon
                        else: colors = np.ones((len(mesh_source.vertices), 3)) * 0.5
                    
                    mesh_data = pv.wrap(mesh_source)

                # Load the '.ply' file
                elif '.ply' in str(mesh_source): mesh_data = pv.read(mesh_source)

            elif isinstance(mesh_source, pv.PolyData):
                mesh_data = mesh_source

            # Save the mesh data to dictionary
            self.mesh_polydata[mesh_name] = (mesh_data, colors)

        if len(self.mesh_polydata) == 1: self.set_reference(reference_name)

    def set_mirror_objects(self, mirror_objects: bool):
        self.mirror_objects = mirror_objects

    def set_image_opacity(self, image_opacity: float):
        self.image_opacity = image_opacity
    
    def set_mesh_opacity(self, surface_opacity: float):
        self.surface_opacity = surface_opacity

    def set_camera_extrinsics(self, cam_position, cam_viewup):
        self.camera.SetPosition((0,0,cam_position))
        self.camera.SetFocalPoint((0,0,0))
        self.camera.SetViewUp(cam_viewup)
    
    def set_camera_intrinsics(self, width, height, cam_focal_length):
        
        # Set camera intrinsic attribute
        self.camera_intrinsics = np.array([
            [cam_focal_length, 0, width/2],
            [0, cam_focal_length, height/2],
            [0, 0, 1]
        ])
        
        cx = self.camera_intrinsics[0,2]
        cy = self.camera_intrinsics[1,2]
        f = self.camera_intrinsics[0,0]
        
        # convert the principal point to window center (normalized coordinate system) and set it
        wcx = -2*(cx - float(width)/2) / width
        wcy =  2*(cy - float(height)/2) / height
        self.camera.SetWindowCenter(wcx, wcy) # (0,0)
        
        # Setting the view angle in degrees
        view_angle = (180 / math.pi) * (2.0 * math.atan2(height/2.0, f)) # or view_angle = np.degrees(2.0 * math.atan2(height/2.0, f))
        self.camera.SetViewAngle(view_angle) # view angle should be in degrees
        
    def set_transformation_matrix(self, matrix:np.ndarray=None, rot:np.ndarray=None, trans:np.ndarray=None):
        
        self.transformation_matrix = matrix if matrix is not None else np.vstack((np.hstack((rot, trans)), [0, 0, 0, 1]))
    
    def set_reference(self, name:str):
        self.reference = name
        
    def set_mesh_info(self, name:str, mesh: trimesh.Trimesh()):
        assert mesh.vertices.shape[1] == 3, "it should be N by 3 matrix"
        assert mesh.faces.shape[1] == 3, "it should be N by 3 matrix"
        setattr(self, f"{name}_mesh", mesh)
        
    # Suitable for total two and above mesh quantities
    def bind_meshes(self, main_mesh: str, key: str):
        
        other_meshes = []
    
        for mesh_name in self.mesh_polydata.keys():
                if mesh_name != main_mesh:
                    other_meshes.append(mesh_name)
            
        self.binded_meshes[main_mesh] = {'key': key, 'meshes': other_meshes}
     # configure event functions
    
    def event_zoom_out(self, *args):
        self.pv_plotter.camera.zoom(0.5)
        logger.debug("event_zoom_out callback complete")

    def event_zoom_in(self, *args):
        self.pv_plotter.camera.zoom(2)
        logger.debug("event_zoom_in callback complete")

    def event_reset_camera(self, *args):
        self.pv_plotter.camera = self.camera.copy()
        logger.debug("reset_camera_event callback complete")
        
    def event_toggle_image_opacity(self, *args, up):
        if up:
            self.image_opacity += 0.2
            if self.image_opacity >= 1:
                self.image_opacity = 1
        else:
            self.image_opacity -= 0.2
            if self.image_opacity <= 0:
                self.image_opacity = 0
        
        self.image_actor.GetProperty().opacity = self.image_opacity
        self.pv_plotter.add_actor(self.image_actor, pickable=False, name="image")

        logger.debug("event_toggle_image_opacity callback complete")
        
    def event_toggle_surface_opacity(self, *args, up):    
        if up:
            self.surface_opacity += 0.2
            if self.surface_opacity > 1:
                self.surface_opacity = 1
        else:
            self.surface_opacity -= 0.2
            if self.surface_opacity < 0:
                self.surface_opacity = 0
                
        transformation_matrix = self.mesh_actors[self.reference].user_matrix
        for actor_name, actor in self.mesh_actors.items():
            actor.user_matrix = transformation_matrix if not "_mirror" in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            actor.GetProperty().opacity = self.surface_opacity
            self.pv_plotter.add_actor(actor, pickable=True, name=actor_name)

        logger.debug("event_toggle_surface_opacity callback complete")
        
    def event_track_registration(self, *args):
        
        transformation_matrix = self.mesh_actors[self.reference].user_matrix
        for actor_name, actor in self.mesh_actors.items():
            actor.user_matrix = transformation_matrix if not "_mirror" in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            self.pv_plotter.add_actor(actor, pickable=True, name=actor_name)
            logger.debug(f"<Actor {actor_name}> RT: \n{actor.user_matrix}")
    
    def event_realign_meshes(self, *args, main_mesh=None, other_meshes=[]):
        
        objs = {'fix' : main_mesh, 'move': other_meshes}
        
        transformation_matrix = self.mesh_actors[f"{objs['fix']}"].user_matrix
        
        for obj in objs['move']:
            self.mesh_actors[f"{obj}"].user_matrix = transformation_matrix if not "_mirror" in obj else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            self.pv_plotter.add_actor(self.mesh_actors[f"{obj}"], pickable=True, name=obj)
        
        logger.debug(f"realign: main => {main_mesh}, others => {other_meshes} complete")
        
    def event_gt_position(self, *args):
        
        for actor_name, actor in self.mesh_actors.items():
            actor.user_matrix = self.initial_poses[actor_name]
            self.pv_plotter.add_actor(actor, pickable=True, name=actor_name)

        logger.debug("event_gt_position callback complete")
        
    def event_update_position(self, *args):
        self.transformation_matrix = self.mesh_actors[self.reference].user_matrix
        for actor_name, actor in self.mesh_actors.items():
            # update the the actor's user matrix
            self.transformation_matrix = self.transformation_matrix if not '_mirror' in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ self.transformation_matrix
            actor.user_matrix = self.transformation_matrix
            self.initial_poses[actor_name] = self.transformation_matrix
            self.pv_plotter.add_actor(actor, pickable=True, name=actor_name)
        
        logger.debug(f"\ncurrent transformation matrix: \n{self.transformation_matrix}")
        logger.debug("event_update_position callback complete")
    
    def plot(self, return_depth_map=False):
        
        if return_depth_map: assert self.off_screen == True, "Should set off_screen to True!"

        if self.reference is None and len(self.mesh_polydata) >= 1: raise RuntimeError("reference name is not set")
        
        # load the mesh pyvista data
        for mesh_name, mesh_info in self.mesh_polydata.items():
            
            mesh_data, colors = mesh_info

            # add the color to pv_plotter
            if not self.off_screen:
                if self.nocs_color: # color array is(2454, 3)
                    mesh = self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=self.surface_opacity, name=mesh_name) if not self.point_clouds else self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=self.surface_opacity, name=mesh_name) #, show_edges=True)
                else: # color array is (2454, )
                    mesh = self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=self.surface_opacity, name=mesh_name) if not self.point_clouds else self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=self.surface_opacity, name=mesh_name) #, show_edges=True)
            else:
                if self.nocs_color:
                    mesh = self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=self.surface_opacity, lighting=False, name=mesh_name) if not self.point_clouds else self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=self.surface_opacity, lighting=False, name=mesh_name) #, show_edges=True)
                else:
                    mesh = self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=self.surface_opacity, lighting=False, name=mesh_name) if not self.point_clouds else self.pv_plotter.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=self.surface_opacity, lighting=False, name=mesh_name) #, show_edges=True)

            # Set the transformation matrix to be the mesh's user_matrix
            mesh.user_matrix = self.transformation_matrix if not self.mirror_objects else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ self.transformation_matrix
            self.initial_poses[mesh_name] = self.transformation_matrix
            
            # Add and save the actor
            actor, _ = self.pv_plotter.add_actor(mesh, pickable=True, name=mesh_name)
            self.mesh_actors[mesh_name] = actor

        # Set the camera initial parameters
        self.pv_plotter.camera = self.camera.copy()
        # check the clipping range
        # print(self.pv_plotter.camera.clipping_range)

        if not self.off_screen:
            self.pv_plotter.enable_joystick_actor_style()
            self.pv_plotter.enable_trackball_actor_style()

            # Register callbacks
            self.pv_plotter.add_key_event('c', self.event_reset_camera)
            self.pv_plotter.add_key_event('z', self.event_zoom_out)
            self.pv_plotter.add_key_event('x', self.event_zoom_in)
            self.pv_plotter.add_key_event('t', self.event_track_registration)

            for main_mesh, mesh_data in self.binded_meshes.items():
                event_func = functools.partial(self.event_realign_meshes, main_mesh=main_mesh, other_meshes=mesh_data['meshes'])
                self.pv_plotter.add_key_event(mesh_data['key'], event_func)
            
            self.pv_plotter.add_key_event('k', self.event_gt_position)
            self.pv_plotter.add_key_event('l', self.event_update_position)
            
            event_toggle_image_opacity_up_func = functools.partial(self.event_toggle_image_opacity, up=True)
            self.pv_plotter.add_key_event('b', event_toggle_image_opacity_up_func)
            event_toggle_image_opacity_down_func = functools.partial(self.event_toggle_image_opacity, up=False)
            self.pv_plotter.add_key_event('n', event_toggle_image_opacity_down_func)
            
            event_toggle_surface_opacity_up_func = functools.partial(self.event_toggle_surface_opacity, up=True)
            self.pv_plotter.add_key_event('y', event_toggle_surface_opacity_up_func)
            event_toggle_surface_opacity_up_func = functools.partial(self.event_toggle_surface_opacity, up=False)
            self.pv_plotter.add_key_event('u', event_toggle_surface_opacity_up_func)
            
            self.pv_plotter.add_axes()
            self.pv_plotter.add_camera_orientation_widget()
            self.pv_plotter.show("vision6D")
        else:
            if len(self.image_polydata) < 1: self.pv_plotter.set_background('black')
            self.pv_plotter.show()
            rendered_image = self.pv_plotter.last_image
            # obtain the depth map
            if return_depth_map: depth_map = self.pv_plotter.get_image_depth()
            return rendered_image if not return_depth_map else (rendered_image, depth_map)