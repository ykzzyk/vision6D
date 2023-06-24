from ...stores import QtStore
from ...stores import PlotStore
from ...stores import MeshStore
from PyQt5 import QtWidgets

from ..panel import DisplayPanel

class RegisterMenu():

    def __init__(self):

        self.plot_store = PlotStore()
        self.qt_store = QtStore()
        self.mesh_store = MeshStore()

        self.display_panel = DisplayPanel()

    def reset_gt_pose(self):
        self.qt_store.output_text.append(f"-> Reset the GT pose to: \n{self.mesh_store.initial_pose}")
        self.mesh_Store.register_pose(self.mesh_store.initial_pose)

    def update_gt_pose(self):
        self.mesh_store.initial_pose = self.mesh_store.transformation_matrix
        self.mesh_store.current_pose()
        self.qt_store.output_text.append(f"Update the GT pose to: \n{self.mesh_store.initial_pose}")
            
    def current_pose(self):
        if self.mesh_store.current_pose():
            self.qt_store.output_text.append(f"-> Current reference mesh is: <span style='background-color:yellow; color:black;'>{self.mesh_store.reference}</span>")
            self.qt_store.output_text.append(f"Current pose is: \n{self.mesh_store.transformation_matrix}")

    def undo_pose(self, actor_name):
        if len(self.mesh_store.undo_poses[actor_name]) != 0: 
            self.mesh_store.undo_pose(actor_name)
            
            self.mesh_store.mesh_actors[actor_name].user_matrix = self.mesh_store.transformation_matrix
            self.plot_store.plotter.add_actor(self.mesh_store.mesh_actors[actor_name], pickable=True, name=actor_name)
            
            self.qt_store.output_text.append(f"-> Current reference mesh is: <span style='background-color:yellow; color:black;'>{actor_name}</span>")
            self.qt_store.output_text.append(f"Undo pose to: \n{self.mesh_store.transformation_matrix}")
            
