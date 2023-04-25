import sys
from typing import List, Dict, Tuple, Optional
import pathlib
import logging
import numpy as np
import math
import trimesh
import functools
import numpy as np
import matplotlib.pyplot as plt
import cv2
import PIL

# Setting the Qt bindings for QtPy
import os
os.environ["QT_API"] = "pyqt5"

from qtpy import QtWidgets
from PyQt5.QtWidgets import QLineEdit, QMessageBox, QPushButton, QInputDialog, QFileDialog 
import pyvista as pv
from pyvistaqt import QtInteractor, MainWindow
import vision6D as vis

np.set_printoptions(suppress=True)

def try_except(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except:
            if isinstance(args[0], MainWindow): QMessageBox.warning(args[0], 'vision6D', "Need to load a mesh first!", QMessageBox.Ok, QMessageBox.Ok)

    return wrapper
    
class MyMainWindow(MainWindow):

    def __init__(self, parent=None, show=True):
        QtWidgets.QMainWindow.__init__(self, parent)
        
        # setting title
        self.setWindowTitle("Vision6D")
        self.showMaximized()
        
        # create the frame
        self.frame = QtWidgets.QFrame()
        vlayout = QtWidgets.QVBoxLayout()

        # add the pyvista interactor object
        self.plotter = QtInteractor(self.frame)
        vlayout.addWidget(self.plotter.interactor)
        self.signal_close.connect(self.plotter.close)

        self.frame.setLayout(vlayout)
        self.setCentralWidget(self.frame)

        # simple menu to demo functions
        mainMenu = self.menuBar()
        # simple dialog to record users input info
        self.input_dialog = QInputDialog()
        self.file_dialog = QFileDialog()
        
        self.initial_dir = pathlib.Path('E:\GitHub\ossicles_6D_pose_estimation\data')
        self.meshdict = {}
        self.image_path = None
        self.mesh_path = None

        os.makedirs(vis.config.GITROOT / "output", exist_ok=True)
        os.makedirs(vis.config.GITROOT / "output" / "mesh", exist_ok=True)
        os.makedirs(vis.config.GITROOT / "output" / "image", exist_ok=True)
            
        # allow to add files
        fileMenu = mainMenu.addMenu('File')
        fileMenu.addAction('Add Image', self.add_image_file)
        fileMenu.addAction('Add Mesh', self.add_mesh_file)
        fileMenu.addAction('Add Pose', self.add_pose_file)
        self.removeMenu = fileMenu.addMenu("Remove")
        fileMenu.addAction('Clear', self.clear_plot)
        fileMenu.addAction('Export Mesh', self.export_mesh_plot)
        fileMenu.addAction('Export Image', self.export_image_plot)

        # Add set attribute menu
        setAttrMenu = mainMenu.addMenu('Set')
        set_reference_name_menu = functools.partial(self.set_attr, info="Set Reference Mesh Name", hints='ossicles')
        setAttrMenu.addAction('Set Reference', set_reference_name_menu)
        set_image_opacity_menu = functools.partial(self.set_attr, info="Set Image Opacity (range from 0 to 1)", hints='0.99')
        setAttrMenu.addAction('Set Image Opacity', set_image_opacity_menu)
        set_mesh_opacity_menu = functools.partial(self.set_attr, info="Set Mesh Opacity (range from 0 to 1)", hints='0.8')
        setAttrMenu.addAction('Set Mesh Opacity', set_mesh_opacity_menu)

        # Add camera related actions
        CameraMenu = mainMenu.addMenu('Camera')
        CameraMenu.addAction('Reset Camera (c)', self.reset_camera)
        CameraMenu.addAction('Zoom In (x)', self.zoom_in)
        CameraMenu.addAction('Zoom Out (z)', self.zoom_out)

        # Add register related actions
        RegisterMenu = mainMenu.addMenu('Regiter')
        RegisterMenu.addAction('Reset GT Pose (k)', self.reset_gt_pose)
        RegisterMenu.addAction('Update GT Pose (l)', self.update_gt_pose)
        RegisterMenu.addAction('Current Pose (t)', self.current_pose)
        RegisterMenu.addAction('Undo Pose (s)', self.undo_pose)

        # Add coloring related actions
        RegisterMenu = mainMenu.addMenu('Color')
        set_nocs_color = functools.partial(self.set_color, True)
        RegisterMenu.addAction('NOCS', set_nocs_color)
        set_latlon_color = functools.partial(self.set_color, False)
        RegisterMenu.addAction('LatLon', set_latlon_color)

        PnPMenu = mainMenu.addMenu('PnP')
        PnPMenu.addAction('EPnP', self.epnp)

        if show:
            self.plotter.set_background('black'); assert self.plotter.background_color == "black", "plotter's background need to be black"
            self.plotter.enable_joystick_actor_style()
            self.plotter.enable_trackball_actor_style()
            self.plotter.track_click_position(callback=self.track_click_callback, side='l')

            # camera related key bindings
            self.plotter.add_key_event('c', self.reset_camera)
            self.plotter.add_key_event('z', self.zoom_out)
            self.plotter.add_key_event('x', self.zoom_in)

            # registration related key bindings
            self.plotter.add_key_event('k', self.reset_gt_pose)
            self.plotter.add_key_event('l', self.update_gt_pose)
            self.plotter.add_key_event('t', self.current_pose)
            self.plotter.add_key_event('s', self.undo_pose)

            self.plotter.add_axes()
            self.plotter.add_camera_orientation_widget()

            self.plotter.show()
            self.show()

    def set_attr(self, info, hints):
        output, ok = self.input_dialog.getText(self, 'Input', info, text=hints)
        info = info.upper()
        if ok: 
            if 'reference'.upper() in info:
                try: self.set_reference(output)
                except AssertionError: QMessageBox.warning(self, 'vision6D', "Reference name does not exist in the paths", QMessageBox.Ok, QMessageBox.Ok)
            elif 'image opacity'.upper() in info:
                try: self.set_image_opacity(float(output))
                except AssertionError: QMessageBox.warning(self, 'vision6D', "Image opacity should range from 0 to 1", QMessageBox.Ok, QMessageBox.Ok)
            elif 'mesh opacity'.upper() in info:
                try: self.set_mesh_opacity(float(output))
                except AssertionError: QMessageBox.warning(self, 'vision6D', "Mesh opacity should range from 0 to 1", QMessageBox.Ok, QMessageBox.Ok)

    def add_image_file(self):
        if self.image_path == None or self.image_path == '':
            self.image_path, _ = self.file_dialog.getOpenFileName(None, "Open file", str(self.initial_dir / "frames"), "Files (*.png *.jpg)")
        else:
            self.image_path, _ = self.file_dialog.getOpenFileName(None, "Open file", str(pathlib.Path(self.image_path).parent), "Files (*.png *.jpg)")

        if self.image_path != '': self.add_image(self.image_path)

    def add_mesh_file(self):
        if self.mesh_path == None or self.mesh_path == '':
            self.mesh_path, _ = self.file_dialog.getOpenFileName(None, "Open file", str(self.initial_dir / "surgical_planning"), "Files (*.mesh *.ply)")
        else:
            self.mesh_path, _ = self.file_dialog.getOpenFileName(None, "Open file", str(pathlib.Path(self.mesh_path).parent), "Files (*.mesh *.ply)")

        if self.mesh_path != '':
            mesh_name, ok = self.input_dialog.getText(self, 'Input', 'Specify the object Class name', text='ossicles')
            if ok: 
                self.meshdict[mesh_name] = self.mesh_path
                self.add_mesh(mesh_name, self.mesh_path)
                if self.reference is None: 
                    reply = QMessageBox.question(self,"vision6D", "Do you want to make this mesh as a reference?", QMessageBox.Yes, QMessageBox.No)
                    if reply == QMessageBox.Yes: self.reference = mesh_name
      
    def add_pose_file(self):
        pose_path, _ = self.file_dialog.getOpenFileName(None, "Open file", str(self.initial_dir / "gt_poses"), "Files (*.npy)")
        if pose_path != '': self.set_transformation_matrix(matrix=np.load(pose_path))
    
    def remove_actor(self, name):
        if self.reference == name: self.reference = None
        if name == 'image': 
            actor = self.image_actor
            self.image_actor = None
        else: actor = self.mesh_actors[name]
        self.plotter.remove_actor(actor)
        actions_to_remove = [action for action in self.removeMenu.actions() if action.text() == name]
        assert len(actions_to_remove) == 1, "the actions to remove should always be 1"
        self.removeMenu.removeAction(actions_to_remove[0])
        # remove the item from the dictionary
        del self.mesh_polydata[name]
        del self.mesh_actors[name]
        if len(self.mesh_actors) == 0: self.undo_poses = []

    def clear_plot(self):
        
        # Clear out everything in the menu
        for action in self.removeMenu.actions():
            name = action.text()
            if name == 'image': actor = self.image_actor
            else: actor = self.mesh_actors[name]
            self.plotter.remove_actor(actor)
            self.removeMenu.removeAction(action)

        # Re-initial the dictionaries
        self.reference = None
        self.transformation_matrix = np.eye(4)
        self.image_actor = None
        self.mesh_polydata = {}
        self.mesh_actors = {}
        self.undo_poses = []

    def export_mesh_plot(self, reply_reset_camera=None, reply_render_mesh=None, reply_export_surface=None, msg=True):

        if self.reference is not None: 
            transformation_matrix = self.mesh_actors[self.reference].user_matrix
        else:
            QMessageBox.warning(self, 'vision6D', "Need to set a reference first!", QMessageBox.Ok, QMessageBox.Ok)
            return 0

        if reply_reset_camera is None and reply_render_mesh is None and reply_export_surface is None:
            reply_reset_camera = QMessageBox.question(self,"vision6D", "Reset Camera?", QMessageBox.Yes, QMessageBox.No)
            reply_render_mesh = QMessageBox.question(self,"vision6D", "Only render the reference mesh?", QMessageBox.Yes, QMessageBox.No)
            reply_export_surface = QMessageBox.question(self,"vision6D", "Export the mesh as surface?", QMessageBox.Yes, QMessageBox.No)
            
        if reply_reset_camera == QMessageBox.Yes: camera = self.camera.copy()
        else: camera = self.plotter.camera.copy()
        if reply_render_mesh == QMessageBox.No: render_all_meshes = True
        else: render_all_meshes = False
        if reply_export_surface == QMessageBox.No: point_clouds = True
        else: point_clouds = False
            
        render = pv.Plotter(window_size=[self.window_size[0], self.window_size[1]], lighting=None, off_screen=True)
        
        # background set to black
        render.set_background('black'); assert render.background_color == "black", "render's background need to be black"
            
        pathname = pathlib.Path(self.mesh_path).stem

        if self.image_actor is not None: 
            id = pathlib.Path(self.image_path).stem.split('_')[-1]
            name = pathlib.Path(self.mesh_path).stem + f'_render_{id}.png'
        else:
            name = pathlib.Path(self.mesh_path).stem + '_render.png'
            
        if render_all_meshes:
            # Render the targeting objects
            for mesh_name, mesh_data in self.mesh_polydata.items():
                colors = mesh_data.point_data.active_scalars
                if colors is None: colors = np.ones((len(mesh_data.points), 3)) * 0.5
                assert colors.shape == mesh_data.points.shape, "colors shape should be the same as mesh_data.points shape"
                mesh = render.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=1, name=mesh_name) if not point_clouds else render.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=1, name=mesh_name)
                mesh.user_matrix = transformation_matrix

            render.camera = camera
            render.disable(); render.show()

            # obtain the rendered image
            image = render.last_image
            output_path = vis.config.GITROOT / "output" / "mesh" / name
            rendered_image = PIL.Image.fromarray(image)
            rendered_image.save(output_path)
            if msg: QMessageBox.about(self,"vision6D", f"Export the image to {str(output_path)}")
        else:
            mesh_name = self.reference
            mesh_data = self.mesh_polydata[mesh_name]
            colors = mesh_data.point_data.active_scalars
            if colors is None: colors = np.ones((len(mesh_data.points), 3)) * 0.5
            assert colors.shape == mesh_data.points.shape, "colors shape should be the same as mesh_data.points shape"
            mesh = render.add_mesh(mesh_data, scalars=colors, rgb=True, style='surface', opacity=1, name=mesh_name) if not point_clouds else render.add_mesh(mesh_data, scalars=colors, rgb=True, style='points', point_size=1, render_points_as_spheres=False, opacity=1, name=mesh_name)
            mesh.user_matrix = transformation_matrix
            render.camera = camera
            render.disable(); render.show()

            # obtain the rendered image
            image = render.last_image
            output_path = vis.config.GITROOT / "output" / "mesh" / name
            rendered_image = PIL.Image.fromarray(image)
            rendered_image.save(output_path)
            if msg: QMessageBox.about(self,"vision6D", f"Export the image to {str(output_path)}")

            return image

    def export_image_plot(self):

        reply = QMessageBox.question(self,"vision6D", "Reset Camera?", QMessageBox.Yes, QMessageBox.No)
        if reply == QMessageBox.Yes: camera = self.camera.copy()
        else: camera = self.plotter.camera.copy()

        if self.image_actor == None:
            QMessageBox.warning(self, 'vision6D', "Need to load an image first!", QMessageBox.Ok, QMessageBox.Ok)
            return 0

        render = pv.Plotter(window_size=[self.window_size[0], self.window_size[1]], lighting=None, off_screen=True)
        render.set_background('black'); assert render.background_color == "black", "render's background need to be black"
        image_actor = self.image_actor.copy(deep=True)
        image_actor.GetProperty().opacity = 1
        render.add_actor(image_actor, pickable=False, name="image")
        render.camera = camera
        render.disable()
        render.show()

        # obtain the rendered image
        image = render.last_image
        name = pathlib.Path(self.image_path).stem + '.png'

        output_path = vis.config.GITROOT / "output" / "image" / name
        rendered_image = PIL.Image.fromarray(image)
        rendered_image.save(output_path)
        QMessageBox.about(self,"vision6D", f"Export the image to {str(output_path)}")

class App(MyMainWindow):
    def __init__(self):
        super().__init__()

        self.window_size = (1920, 1080)
        self.mirror_objects = False

        self.reference = None
        self.transformation_matrix = np.eye(4)

        # initial the dictionaries
        self.image_actor = None
        self.mesh_polydata = {}
        self.mesh_actors = {}
        self.undo_poses = []
        
        # default opacity for image and surface
        self.set_image_opacity(0.99) # self.image_opacity = 0.35
        self.set_mesh_opacity(0.8) # self.surface_opacity = 1

        # Set up the camera
        self.camera = pv.Camera()
        self.cam_focal_length = 50000
        self.cam_viewup = (0, -1, 0)
        self.cam_position = -500 # -500mm
        self.set_camera_intrinsics(self.window_size[0], self.window_size[1], self.cam_focal_length)
        self.set_camera_extrinsics(self.cam_position, self.cam_viewup)

        self.plotter.camera = self.camera.copy()

    def set_reference(self, name:str):     
        assert name in self.meshdict.keys(), "reference name is not in the path!"
        self.reference = name
  
    def set_transformation_matrix(self, matrix:np.ndarray=None, rot:np.ndarray=None, trans:np.ndarray=None):
        if matrix is None: matrix = np.vstack((np.hstack((rot, trans)), [0, 0, 0, 1]))
        self.transformation_matrix = matrix
        self.initial_pose = self.transformation_matrix
        self.reset_gt_pose()
        self.reset_camera()

    def set_image_opacity(self, image_opacity: float):
        assert image_opacity>=0 and image_opacity<=1, "image opacity should range from 0 to 1!"
        self.image_opacity = image_opacity
        if self.image_actor is not None:
            self.image_actor.GetProperty().opacity = self.image_opacity
            self.plotter.add_actor(self.image_actor, pickable=False, name="image")

    def set_mesh_opacity(self, surface_opacity: float):
        assert surface_opacity>=0 and surface_opacity<=1, "mesh opacity should range from 0 to 1!"
        self.surface_opacity = surface_opacity
        for actor_name, actor in self.mesh_actors.items():
            actor.user_matrix = pv.array_from_vtkmatrix(actor.GetMatrix())
            actor.GetProperty().opacity = self.surface_opacity
            self.plotter.add_actor(actor, pickable=True, name=actor_name)
    
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

    def add_image(self, file_path):

        """ add a image to the pyqt frame """
        image_source = np.array(PIL.Image.open(file_path))
        image = pv.UniformGrid(dimensions=(1920, 1080, 1), spacing=[0.01,0.01,1], origin=(0.0, 0.0, 0.0))
        image.point_data["values"] = image_source.reshape((1920*1080, 3)) # order = 'C
        image = image.translate(-1 * np.array(image.center), inplace=False)

        # Then add it to the plotter
        image = self.plotter.add_mesh(image, rgb=True, opacity=self.image_opacity, name='image')
        actor, _ = self.plotter.add_actor(image, pickable=False, name="image")

        # Save actor for later
        self.image_actor = actor 

        # add remove current image to removeMenu
        remove_actor = functools.partial(self.remove_actor, self.image_actor.name)
        self.removeMenu.addAction(self.image_actor.name, remove_actor)

    def add_mesh(self, mesh_name, mesh_path):
        """ add a mesh to the pyqt frame """
                              
        if isinstance(mesh_path, pathlib.WindowsPath) or isinstance(mesh_path, str):
            # Load the '.mesh' file
            if '.mesh' in str(mesh_path): 
                mesh_path = vis.utils.load_trimesh(mesh_path)
                assert (mesh_path.vertices.shape[1] == 3 and mesh_path.faces.shape[1] == 3), "it should be N by 3 matrix"
                # Set vertices and faces attribute
                setattr(self, f"{mesh_name}_mesh", mesh_path)
                mesh_data = pv.wrap(mesh_path)

            # Load the '.ply' file
            elif '.ply' in str(mesh_path): mesh_data = pv.read(mesh_path)

        self.mesh_polydata[mesh_name] = mesh_data

        mesh = self.plotter.add_mesh(mesh_data, opacity=self.surface_opacity, name=mesh_name)

        mesh.user_matrix = self.transformation_matrix if not self.mirror_objects else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ self.transformation_matrix
        self.initial_pose = mesh.user_matrix
                
        # Add and save the actor
        actor, _ = self.plotter.add_actor(mesh, pickable=True, name=mesh_name)
        
        assert actor.name == mesh_name, "actor's name should equal to mesh_name"
        
        self.mesh_actors[mesh_name] = actor

        # add remove current mesh to removeMenu
        remove_actor_menu = functools.partial(self.remove_actor, mesh_name)
        self.removeMenu.addAction(mesh_name, remove_actor_menu)

    def reset_camera(self, *args):
        self.plotter.camera = self.camera.copy()

    def zoom_in(self, *args):
        self.plotter.camera.zoom(2)

    def zoom_out(self, *args):
        self.plotter.camera.zoom(0.5)

    def track_click_callback(self, *args):
        if len(self.undo_poses) > 20: self.undo_poses.pop(0)
        if self.reference is not None: self.undo_poses.append(self.mesh_actors[self.reference].user_matrix)

    @try_except
    def reset_gt_pose(self, *args):
        print(f"\nRT: \n{self.initial_pose}\n")
        for actor_name, actor in self.mesh_actors.items():
            actor.user_matrix = self.initial_pose
            self.plotter.add_actor(actor, pickable=True, name=actor_name)

    def update_gt_pose(self, *args):
        if self.reference is not None:
            self.transformation_matrix = self.mesh_actors[self.reference].user_matrix
            self.initial_pose = self.transformation_matrix
            print(f"\nRT: \n{self.initial_pose}\n")
            for actor_name, actor in self.mesh_actors.items():
                # update the the actor's user matrix
                self.transformation_matrix = self.transformation_matrix if not '_mirror' in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ self.transformation_matrix
                actor.user_matrix = self.transformation_matrix
                self.plotter.add_actor(actor, pickable=True, name=actor_name)

    def current_pose(self, *args):
        if self.reference is not None:
            transformation_matrix = self.mesh_actors[self.reference].user_matrix
            print(f"\nRT: \n{transformation_matrix}\n")
            for actor_name, actor in self.mesh_actors.items():
                actor.user_matrix = transformation_matrix if not "_mirror" in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
                self.plotter.add_actor(actor, pickable=True, name=actor_name)

    def undo_pose(self, *args):
        if len(self.undo_poses) != 0: 
            transformation_matrix = self.undo_poses.pop()
            if (transformation_matrix == self.mesh_actors[self.reference].user_matrix).all():
                if len(self.undo_poses) != 0: transformation_matrix = self.undo_poses.pop()
            for actor_name, actor in self.mesh_actors.items():
                actor.user_matrix = transformation_matrix if not "_mirror" in actor_name else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
                self.plotter.add_actor(actor, pickable=True, name=actor_name)

    def set_color(self, nocs_color):
        for mesh_name, mesh_data in self.mesh_polydata.items():
            # get the corresponding color
            colors = vis.utils.color_mesh(mesh_data.points, nocs=nocs_color)
            if colors.shape != mesh_data.points.shape: colors = np.ones((len(mesh_data.points), 3)) * 0.5
            assert colors.shape == mesh_data.points.shape, "colors shape should be the same as mesh_data.points shape"
            
            # color the mesh and actor
            mesh = self.plotter.add_mesh(mesh_data, scalars=colors, rgb=True, opacity=self.surface_opacity, name=mesh_name)
            transformation_matrix = pv.array_from_vtkmatrix(self.mesh_actors[mesh_name].GetMatrix())
            mesh.user_matrix = transformation_matrix if not self.mirror_objects else np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            actor, _ = self.plotter.add_actor(mesh, pickable=True, name=mesh_name)
            assert actor.name == mesh_name, "actor's name should equal to mesh_name"
            self.mesh_actors[mesh_name] = actor

    def epnp(self):
        if self.reference is not None:
            colors = self.mesh_polydata[self.reference].point_data.active_scalars
            if colors is None or (np.all(colors == colors[0])):
                QMessageBox.warning(self, 'vision6D', "The mesh need to be colored with nocs or latlon with gradient color", QMessageBox.Ok, QMessageBox.Ok)
                return 0

            color_mask = self.export_mesh_plot(QMessageBox.Yes, QMessageBox.Yes, QMessageBox.Yes, msg=False)
            gt_pose = self.mesh_actors[self.reference].user_matrix
            pts3d, pts2d = vis.utils.create_2d_3d_pairs(color_mask, self.mesh_polydata[self.reference].points)
            pts2d = pts2d.astype('float32')
            pts3d = pts3d.astype('float32')
            camera_intrinsics = self.camera_intrinsics.astype('float32')
            predicted_pose = vis.utils.solve_epnp_cv2(pts2d, pts3d, camera_intrinsics, self.camera.position)
            error = np.sum(np.abs(predicted_pose - gt_pose))
            QMessageBox.about(self,"vision6D", f"PREDICTED POSE: \n{predicted_pose}\nGT POSE: \n{gt_pose}\nERROR: \n{error}")

        else:
            QMessageBox.warning(self, 'vision6D', "A mesh need to be loaded!", QMessageBox.Ok, QMessageBox.Ok)

if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = App()
    sys.exit(app.exec_())