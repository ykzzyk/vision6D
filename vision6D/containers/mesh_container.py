'''
@author: Yike (Nicole) Zhang
@license: (C) Copyright.
@contact: yike.zhang@vanderbilt.edu
@software: Vision6D
@file: mesh_container.py
@time: 2023-07-03 20:27
@desc: create container for mesh related actions in application
'''
import os
import ast
import copy
import pathlib

import trimesh
import PIL.Image
import matplotlib
import numpy as np
import pyvista as pv

import vtk.util.numpy_support as vtknp

from PyQt5 import QtWidgets

from ..tools import utils
from ..tools import exception
from ..components import CameraStore
from ..components import MaskStore
from ..components import MeshStore
from ..widgets import GetPoseDialog

from ..path import PKG_ROOT

class MeshContainer:
    def __init__(self, 
                color_button, 
                plotter, 
                hintLabel, 
                track_actors_names, 
                add_button_actor_name, 
                button_group_actors_names,
                check_button,
                opacity_spinbox, 
                opacity_value_change,
                reset_camera,
                toggle_register,
                load_mask,
                output_text):
        
        self.ignore_opacity_change = False
        self.toggle_hide_meshes_flag = False

        self.color_button = color_button
        self.plotter = plotter
        self.hintLabel = hintLabel
        self.track_actors_names = track_actors_names
        self.add_button_actor_name = add_button_actor_name
        self.button_group_actors_names = button_group_actors_names
        self.check_button = check_button
        self.opacity_spinbox = opacity_spinbox
        self.opacity_value_change = opacity_value_change
        self.reset_camera = reset_camera
        self.toggle_register = toggle_register
        self.load_mask = load_mask
        self.output_text = output_text
        
        self.camera_store = CameraStore()
        self.mask_store = MaskStore()
        self.mesh_store = MeshStore()

    def add_mesh_file(self, mesh_path='', prompt=False):
        if prompt: 
            mesh_path, _ = QtWidgets.QFileDialog().getOpenFileName(None, "Open file", "", "Files (*.mesh *.ply *.stl *.obj *.off *.dae *.fbx *.3ds *.x3d)") 
        if mesh_path:
            self.hintLabel.hide()
            mesh_data = self.mesh_store.add_mesh(mesh_source=mesh_path)
            if mesh_data: self.add_mesh(mesh_data, np.eye(4))
            else: QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "The mesh format is not supported!", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)

    def mirror_mesh(self, name, direction):
        if self.mesh_store.toggle_anchor_mesh: name = self.mesh_store.reference
        mesh_data = self.mesh_store.meshes[name]
        if direction == 'x': mesh_data.mirror_x = not mesh_data.mirror_x
        elif direction == 'y': mesh_data.mirror_y = not mesh_data.mirror_y
        if mesh_data.initial_pose is None: mesh_data.initial_pose = mesh_data.actor.user_matrix
        transformation_matrix = mesh_data.initial_pose
        if mesh_data.mirror_x: transformation_matrix = np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
        if mesh_data.mirror_y: transformation_matrix = np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
        mesh_data.actor.user_matrix = transformation_matrix
        self.check_button(name=name, output_text=False)
        self.output_text.append(f"-> Mirrored transformation matrix is: \n{transformation_matrix}")

    def add_mesh(self, mesh_data, transformation_matrix):
        """ add a mesh to the pyqt frame """
        mesh = self.plotter.add_mesh(mesh_data.pv_mesh, color=mesh_data.color, opacity=mesh_data.opacity, name=mesh_data.name)
        mesh.user_matrix = transformation_matrix
        actor, _ = self.plotter.add_actor(mesh, pickable=True, name=mesh_data.name)
        mesh_data.actor = actor
        self.color_button.setText(mesh_data.color)

        # add remove current mesh to removeMenu
        if mesh_data.name not in self.track_actors_names:
            self.track_actors_names.append(mesh_data.name)
            self.add_button_actor_name(mesh_data.name)
        #* very important for mirroring
        self.check_button(name=mesh_data.name, output_text=False) 
        
    def anchor_mesh(self):
        self.mesh_store.toggle_anchor_mesh = not self.mesh_store.toggle_anchor_mesh
                
    def set_spacing(self):
        checked_button = self.button_group_actors_names.checkedButton()
        if checked_button:
            name = checked_button.text()
            if name in self.mesh_store.meshes:
                mesh_data = self.mesh_store.meshes[name]
                spacing, ok = QtWidgets.QInputDialog().getText(QtWidgets.QMainWindow(), 'Input', "Set Spacing", text=str(mesh_data.spacing))
                if ok:
                    mesh_data.spacing = exception.set_spacing(spacing)
                    vertices = mesh_data.source_mesh.vertices * mesh_data.spacing
                    mesh_data.pv_mesh.points = vertices
            else:
                QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to select a mesh object instead", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to select a mesh actor first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)
      
    def set_color(self, color, name):
        mesh_data = self.mesh_store.meshes[name]
        if color in self.mesh_store.colors:
            mesh_data.actor.GetMapper().SetScalarVisibility(0)
            mesh_data.actor.GetProperty().SetColor(matplotlib.colors.to_rgb(color))
        else:
            scalars = utils.color_mesh(mesh_data.pv_mesh.points, color=color)
            mapper = mesh_data.actor.GetMapper()
            # if using the original 2454 vertices value, it does not do face rendering
            lut = utils.reset_vtk_lut(colormap="viridis")
            # lut = utils.reset_vtk_lut(colormap=scalars)
            mapper.SetLookupTable(lut)
            mapper.SetScalarVisibility(1)
            mapper.GetInput().GetPointData().SetScalars(vtknp.numpy_to_vtk(scalars)) # VTK lookup map is different from the pyvista lookup map
                    
    def set_mesh_opacity(self, name: str, surface_opacity: float):
        mesh_data = self.mesh_store.meshes[name]
        mesh_data.opacity = surface_opacity
        mesh_data.actor.user_matrix = pv.array_from_vtkmatrix(mesh_data.actor.GetMatrix())
        mesh_data.actor.GetProperty().opacity = surface_opacity

    def toggle_surface_opacity(self, up):
        checked_button = self.button_group_actors_names.checkedButton()
        if checked_button:
            if checked_button.text() in self.mesh_store.meshes: 
                change = 0.05
                if not up: change *= -1
                current_opacity = self.opacity_spinbox.value()
                current_opacity += change
                current_opacity = np.clip(current_opacity, 0, 1)
                self.opacity_spinbox.setValue(current_opacity)
                
    def handle_hide_meshes_opacity(self, flag):
        checked_button = self.button_group_actors_names.checkedButton()
        checked_name = checked_button.text() if checked_button else None
        for button in self.button_group_actors_names.buttons():
            name = button.text()
            if name not in self.mesh_store.meshes: continue
            if len(self.mesh_store.meshes) != 1 and name == checked_name: continue
            mesh_data = self.mesh_store.meshes[name]
            if flag:
                self.ignore_opacity_change = True
                self.opacity_spinbox.setValue(0)
                self.ignore_opacity_change = False
                mesh_data.previous_opacity = mesh_data.opacity
                mesh_data.opacity = 0
                self.set_mesh_opacity(name, mesh_data.opacity)
            else:
                self.ignore_opacity_change = True
                self.opacity_spinbox.setValue(mesh_data.previous_opacity)
                self.ignore_opacity_change = False
                self.set_mesh_opacity(name, mesh_data.previous_opacity)
                mesh_data.previous_opacity = mesh_data.opacity
            
    def toggle_hide_meshes_button(self):
        self.toggle_hide_meshes_flag = not self.toggle_hide_meshes_flag
        self.handle_hide_meshes_opacity(self.toggle_hide_meshes_flag)
                            
    def add_pose_file(self, pose_path):
        if pose_path:
            self.hintLabel.hide()
            transformation_matrix = np.load(pose_path)
            mesh_data = self.mesh_store.meshes[self.mesh_store.reference]
            if mesh_data.mirror_x: transformation_matrix = np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            if mesh_data.mirror_y: transformation_matrix = np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
            self.add_pose(matrix=transformation_matrix)

    def add_pose(self, matrix:np.ndarray=None, rot:np.ndarray=None, trans:np.ndarray=None):
        if matrix is None and (rot is not None and trans is not None): matrix = np.vstack((np.hstack((rot, trans)), [0, 0, 0, 1]))
        if self.mesh_store.toggle_anchor_mesh:
            for mesh_data in self.mesh_store.meshes.values(): mesh_data.initial_pose = matrix
        else: self.mesh_store.meshes[self.mesh_store.reference].initial_pose = matrix
        self.reset_gt_pose()
        
    def set_pose(self):
        mesh_data = self.mesh_store.meshes[self.mesh_store.reference]
        get_pose_dialog = GetPoseDialog(mesh_data.actor.user_matrix)
        res = get_pose_dialog.exec_()
        if res == QtWidgets.QDialog.Accepted:
            if "," not in get_pose_dialog.user_text:
                get_pose_dialog.user_text = get_pose_dialog.user_text.replace(" ", ",")
                get_pose_dialog.user_text = get_pose_dialog.user_text.strip().replace("[,", "[")
            gt_pose = np.array(exception.set_pose(get_pose_dialog.user_text, mesh_data.actor.user_matrix))
            if gt_pose.shape == (4, 4):
                self.hintLabel.hide()
                transformation_matrix = gt_pose
                if mesh_data.mirror_x: transformation_matrix = np.array([[-1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
                if mesh_data.mirror_y: transformation_matrix = np.array([[1, 0, 0, 0], [0, -1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]) @ transformation_matrix
                self.add_pose(matrix=transformation_matrix)
            else:
                QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "It needs to be a 4 by 4 matrix", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok) 
    # todo: fix the reset gt_pose for not anchored situation
    def reset_gt_pose(self):
        if self.mesh_store.reference:
            mesh_data = self.mesh_store.meshes[self.mesh_store.reference]
            if mesh_data.initial_pose is not None:
                self.output_text.append(f"-> Reset the GT pose to: \n{mesh_data.initial_pose}")
                self.toggle_register(mesh_data.initial_pose)
                self.reset_camera()
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to set a reference mesh first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)

    # todo: fix the update gt_pose for not anchored situation
    def update_gt_pose(self):
        if self.mesh_store.reference:
            mesh_data = self.mesh_store.meshes[self.mesh_store.reference]
            if mesh_data.initial_pose is not None:
                mesh_data.initial_pose = mesh_data.actor.user_matrix
                self.toggle_register(mesh_data.actor.user_matrix)
                self.output_text.append(f"-> Update the {self.mesh_store.reference} GT pose to: \n{mesh_data.initial_pose}")
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to set a reference mesh first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)

    def undo_actor_pose(self):
        if self.button_group_actors_names.checkedButton():
            name = self.button_group_actors_names.checkedButton().text()
            if name in self.mesh_store.meshes:
                self.mesh_store.undo_actor_pose(name)
                #very important, donnot change this line to "toggle_register"
                self.check_button(name=name)
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Choose a mesh actor first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)

    def export_mesh_pose(self):
        for mesh_data in self.mesh_store.meshes.values():
            if self.mesh_store.toggle_anchor_mesh: 
                pose = mesh_data.actor.user_matrix
                os.makedirs(PKG_ROOT.parent / "output" / "export_pose", exist_ok=True)
                output_path = PKG_ROOT.parent / "output" / "export_pose" / (mesh_data.name + '.npy')
                # self.update_gt_pose() # todo: donnot know if this is necessary
                np.save(output_path, pose)
                self.output_text.append(f"Export {mesh_data.name} pose to:\n {output_path}")
            else:
                verts, faces = utils.get_mesh_actor_vertices_faces(mesh_data.actor)
                vertices = utils.transform_vertices(verts, mesh_data.actor.user_matrix)
                os.makedirs(PKG_ROOT.parent / "output" / "export_mesh", exist_ok=True)
                output_path = PKG_ROOT.parent / "output" / "export_mesh" / (mesh_data.name + '.ply')
                mesh = trimesh.Trimesh(vertices, faces, process=False)
                ply_file = trimesh.exchange.ply.export_ply(mesh)
                with open(output_path, "wb") as fid: fid.write(ply_file)
                self.output_text.append(f"Export {mesh_data.name} mesh to:\n {output_path}")
            
    def export_mesh_render(self, save_render=True):
        image = None
        if self.mesh_store.reference:
            image = self.mesh_store.render_mesh(camera=self.plotter.camera.copy())
            if save_render:
                output_path, _ = QtWidgets.QFileDialog.getSaveFileName(QtWidgets.QMainWindow(), "Save File", "", "Mesh Files (*.png)")
                if output_path:
                    if pathlib.Path(output_path).suffix == '': output_path = pathlib.Path(output_path).parent / (pathlib.Path(output_path).stem + '.png')
                    rendered_image = PIL.Image.fromarray(image)
                    rendered_image.save(output_path)
                    self.output_text.append(f"-> Export mesh render to:\n {output_path}")
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to load a mesh first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)
        return image

    def export_segmesh_render(self):
        if self.mesh_store.reference and self.mask_store.mask_actor:
            output_path, _ = QtWidgets.QFileDialog.getSaveFileName(QtWidgets.QMainWindow(), "Save File", "", "SegMesh Files (*.png)")
            if output_path:
                if pathlib.Path(output_path).suffix == '': output_path = pathlib.Path(output_path).parent / (pathlib.Path(output_path).stem + '.png')
                mask_surface = self.mask_store.update_mask()
                self.load_mask(mask_surface)
                segmask = self.mask_store.render_mask(camera=self.plotter.camera.copy())
                if np.max(segmask) > 1: segmask = segmask / 255
                image = self.mesh_store.render_mesh(camera=self.plotter.camera.copy())
                image = (image * segmask).astype(np.uint8)
                rendered_image = PIL.Image.fromarray(image)
                rendered_image.save(output_path)
                self.output_text.append(f"-> Export segmask render:\n to {output_path}")
        else:
            QtWidgets.QMessageBox.warning(QtWidgets.QMainWindow(), 'vision6D', "Need to load a mesh or mask first", QtWidgets.QMessageBox.Ok, QtWidgets.QMessageBox.Ok)
            return 0
