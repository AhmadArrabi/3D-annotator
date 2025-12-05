import os
import sys
import numpy as np
import nibabel as nib
import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector, Button

class Annotator:
    def __init__(self, data_path):
        self.data_path = data_path
        self.img = nib.load(data_path)
        # Reorient to canonical (RAS+)
        self.img = nib.as_closest_canonical(self.img)
        self.data = self.img.get_fdata()
        self.voxel_sizes = self.img.header.get_zooms()
        
        self.ap_view = None
        self.lat_view = None
        
        # Store bounding boxes: [x_min, x_max, y_min, y_max]
        self.ap_box = None
        self.lat_box = None

        self.fig = None
        self.ax_ap = None
        self.ax_lat = None
        
        self.compute_aips()

    def compute_aips(self):
        """
        Compute Average Intensity Projections (AIPs).
        Assumptions after canonical reorientation:
        X (0): Right (+X)
        Y (1): Anterior (+Y)
        Z (2): Superior (+Z)
        
        AP View: Project along Y. Result (X, Z). Transpose to (Z, X) for Image (Rows=Z, Cols=X).
        Lat View: Project along X. Result (Y, Z). Transpose to (Z, Y) for Image (Rows=Z, Cols=Y).
        """
        # AP View: Average along Y axis (1)
        # Result shape (X, Z). T -> (Z, X).
        self.ap_view = np.mean(self.data, axis=1).T
        
        # Lat View: Average along X axis (0)
        # Result shape (Y, Z). T -> (Z, Y).
        self.lat_view = np.mean(self.data, axis=0).T

    def setup_gui(self):
        self.fig, (self.ax_ap, self.ax_lat) = plt.subplots(1, 2, figsize=(12, 6))
        
        # Show AP
        # Origin lower means index (0,0) is bottom-left. 
        # For (Z, X) array: Row 0 is Z=0. Col 0 is X=0.
        # So Z is vertical (up), X is horizontal (right). Correct.
        self.ax_ap.imshow(self.ap_view, cmap='gray', aspect='auto', origin='lower')
        self.ax_ap.set_title('AP View (Posterior-Anterior)')
        self.ax_ap.set_xlabel('X axis')
        self.ax_ap.set_ylabel('Z axis')
        
        # Show Lat
        self.ax_lat.imshow(self.lat_view, cmap='gray', aspect='auto', origin='lower')
        self.ax_lat.set_title('Lateral View (Left-Right)')
        self.ax_lat.set_xlabel('Y axis')
        self.ax_lat.set_ylabel('Z axis')

        # Add Selectors
        self.rs_ap = RectangleSelector(self.ax_ap, self.on_select_ap,
                                       useblit=True,
                                       button=[1], 
                                       minspanx=5, minspany=5,
                                       spancoords='pixels',
                                       interactive=True)
        
        self.rs_lat = RectangleSelector(self.ax_lat, self.on_select_lat,
                                       useblit=True,
                                       button=[1], 
                                       minspanx=5, minspany=5,
                                       spancoords='pixels',
                                       interactive=True)
        
        # Confirm Button
        ax_confirm = plt.axes([0.8, 0.01, 0.1, 0.05])
        self.b_confirm = Button(ax_confirm, 'Confirm')
        self.b_confirm.on_clicked(self.confirm)

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.1)
        # plt.show() removed

    def on_select_ap(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        self.ap_box = (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)) # x_min, x_max, z_min, z_max
        print(f"AP Box (X, Z): {self.ap_box}")

    def on_select_lat(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        self.lat_box = (min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)) # y_min, y_max, z_min, z_max
        print(f"Lat Box (Y, Z): {self.lat_box}")

    def confirm(self, event):
        if self.ap_box is None and self.lat_box is None:
             print("Please draw at least one bounding box.")
             return
             
        # Initialize coordinates
        cx = self.data.shape[0] // 2
        cy = self.data.shape[1] // 2
        cz = self.data.shape[2] // 2
        
        # AP Box gives X and Z
        if self.ap_box:
            # Box is (min_x, max_x, min_y, max_y) in plot coords
            # Plot X is Data X. Plot Y is Data Z.
            x_min, x_max, z_min, z_max = self.ap_box
            cx = (x_min + x_max) / 2
            cz = (z_min + z_max) / 2
            
        # Lat Box gives Y and Z
        if self.lat_box:
            # Box is (min_x, max_x, min_y, max_y) in plot coords
            # Plot X is Data Y. Plot Y is Data Z.
            y_min, y_max, z_min_lat, z_max_lat = self.lat_box
            cy = (y_min + y_max) / 2
            # Average Z if both available
            if self.ap_box:
                cz_lat = (z_min_lat + z_max_lat) / 2
                cz = (cz + cz_lat) / 2
            else:
                cz = (z_min_lat + z_max_lat) / 2
        
        print(f"Calculated Center: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}")
        self.show_mprs((cx, cy, cz))

    def show_mprs(self, center):
        cx, cy, cz = int(center[0]), int(center[1]), int(center[2])
        
        # Clamp coordinates
        cx = max(0, min(cx, self.data.shape[0]-1))
        cy = max(0, min(cy, self.data.shape[1]-1))
        cz = max(0, min(cz, self.data.shape[2]-1))
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Axial (Z=constant)
        # Data slice (X, Y).
        # We want X horizontal, Y vertical.
        # Transpose -> (Y, X). imshow(..., origin='lower') -> Row 0 (Y=0 bottom), Col 0 (X=0 left). Correct.
        if 0 <= cz < self.data.shape[2]:
            ax_img = self.data[:, :, cz].T
            axes[0].imshow(ax_img, cmap='gray', origin='lower')
            axes[0].set_title(f'Axial (Z={cz})')
            axes[0].set_xlabel('X')
            axes[0].set_ylabel('Y')
            # Plot crosshair
            axes[0].axvline(cx, color='r')
            axes[0].axhline(cy, color='r')
            
        # Coronal (Y=constant) -> AP View basically
        # Data slice (X, Z).
        # Transpose -> (Z, X).
        if 0 <= cy < self.data.shape[1]:
            cor_img = self.data[:, cy, :].T
            axes[1].imshow(cor_img, cmap='gray', origin='lower')
            axes[1].set_title(f'Coronal (Y={cy})')
            axes[1].set_xlabel('X')
            axes[1].set_ylabel('Z')
            axes[1].axvline(cx, color='r')
            axes[1].axhline(cz, color='r')
            
        # Sagittal (X=constant) -> Lat View
        # Data slice (Y, Z).
        # Transpose -> (Z, Y).
        if 0 <= cx < self.data.shape[0]:
            sag_img = self.data[cx, :, :].T
            axes[2].imshow(sag_img, cmap='gray', origin='lower')
            axes[2].set_title(f'Sagittal (X={cx})')
            axes[2].set_xlabel('Y')
            axes[2].set_ylabel('Z')
            axes[2].axvline(cy, color='r')
            axes[2].axhline(cz, color='r')
            
        plt.tight_layout()
        if not hasattr(self, 'test_mode') or not self.test_mode:
             plt.show()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Run in test mode (no GUI loop)')
    args = parser.parse_args()

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    files = [f for f in os.listdir(data_dir) if f.endswith('.nii.gz')]
    if files:
        file_path = os.path.join(data_dir, files[0])
        print(f"Loading {file_path}")
        annotator = Annotator(file_path)
        if args.test:
            annotator.test_mode = True
            # Generate figures but don't show
            annotator.setup_gui()
            print("Test run successful, saving figure to test_output.png")
            plt.savefig("test_output.png")
        else:
            annotator.setup_gui()
            # plt.show() logic handled inside if I attach test_mode, or I can add explicit wait here if needed
            # But plt.show() is better in setup_gui or wrapper.
            # I added logic in show_mprs to check test_mode, but for setup_gui I removed it.
            # I should add plt.show() call here for normal mode.
            plt.show()
