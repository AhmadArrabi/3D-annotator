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
        # 3. Aspect Ratio Calculation
        # Voxel sizes: (dx, dy, dz)
        dx, dy, dz = self.voxel_sizes
        
        # AP View (Z vs X): Aspect = dz/dx
        self.aspect_ap = dz / dx
        # Lat View (Z vs Y): Aspect = dz/dy
        self.aspect_lat = dz / dy
        # Axial (Y vs X): Aspect = dy/dx
        self.aspect_axial = dy / dx

        # Layout: 3 columns.
        # Col 0: AP (Span all rows)
        # Col 1: Lat (Span all rows)
        # Col 2: Stacked MPRs (Rows 0, 1, 2)
        # To give more space to AP/Lat, we can adjust width_ratios.
        self.fig = plt.figure(figsize=(18, 10))
        gs = self.fig.add_gridspec(3, 3, width_ratios=[1, 1, 0.6])
        
        # Main Views
        self.ax_ap = self.fig.add_subplot(gs[:, 0])
        self.ax_lat = self.fig.add_subplot(gs[:, 1], sharey=self.ax_ap)
        
        # MPR Views (Stacked)
        self.ax_axial = self.fig.add_subplot(gs[0, 2])
        self.ax_coronal = self.fig.add_subplot(gs[1, 2])
        self.ax_sagittal = self.fig.add_subplot(gs[2, 2])

        # Show AP
        self.ax_ap.imshow(self.ap_view, cmap='gray', aspect=self.aspect_ap, origin='lower')
        self.ax_ap.set_title('AP View (Posterior-Anterior)')
        self.ax_ap.set_xlabel('X axis')
        self.ax_ap.set_ylabel('Z axis')
        
        # Show Lat
        self.ax_lat.imshow(self.lat_view, cmap='gray', aspect=self.aspect_lat, origin='lower')
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
        
        # Z-locking lines
        self.z_lines_lat = [self.ax_lat.axhline(0, color='blue', linestyle='--', alpha=0),
                            self.ax_lat.axhline(0, color='blue', linestyle='--', alpha=0)]
        self.z_lines_ap = [self.ax_ap.axhline(0, color='blue', linestyle='--', alpha=0),
                           self.ax_ap.axhline(0, color='blue', linestyle='--', alpha=0)]

        # Confirm Button position (floating bottom right of middle column?)
        # Or just use an axes outside the grid.
        # Let's put it on the bottom of the second column
        ax_confirm = plt.axes([0.45, 0.02, 0.1, 0.04])
        self.b_confirm = Button(ax_confirm, 'Confirm')
        self.b_confirm.on_clicked(self.confirm)

        plt.tight_layout()
        plt.subplots_adjust(bottom=0.08) # Make room for button
        if not hasattr(self, 'test_mode') or not self.test_mode:
             plt.show()

    def update_z_lines(self, z_min, z_max, source='ap'):
        """Update visual Z-locking lines."""
        if source == 'ap':
            # Update lines on Lat
            self.z_lines_lat[0].set_ydata([z_min]*2)
            self.z_lines_lat[0].set_alpha(1)
            self.z_lines_lat[1].set_ydata([z_max]*2)
            self.z_lines_lat[1].set_alpha(1)
            self.fig.canvas.draw_idle()
        else:
             # Update lines on AP
            self.z_lines_ap[0].set_ydata([z_min]*2)
            self.z_lines_ap[0].set_alpha(1)
            self.z_lines_ap[1].set_ydata([z_max]*2)
            self.z_lines_ap[1].set_alpha(1)
            self.fig.canvas.draw_idle()           

    def on_select_ap(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        z_min, z_max = min(y1, y2), max(y1, y2)
        
        # Force Z lock if Lat exists? Or just update Z-range
        self.ap_box = (min(x1, x2), max(x1, x2), z_min, z_max)
        self.update_z_lines(z_min, z_max, source='ap')
        
        # If Lat box exists, snap it
        if self.lat_box:
            y_min_l, y_max_l, _, _ = self.lat_box
            # self.rs_lat.extents = (y_min_l, y_max_l, z_min, z_max) # This might trigger callback loop?
            # RectangleSelector doesn't easily allow programmatic update without triggering events unless careful.
            # For now, just let the calculation use the new Z.
            pass

        print(f"AP Box (X={self.ap_box[0]:.1f}-{self.ap_box[1]:.1f}, Z={z_min:.1f}-{z_max:.1f})")

    def on_select_lat(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        y_min, y_max = min(x1, x2), max(x1, x2)
        z_min_curr, z_max_curr = min(y1, y2), max(y1, y2)

        # 2. Lock Z from AP if AP exists
        if self.ap_box:
            _, _, z_min_lock, z_max_lock = self.ap_box
            print("Snapping Lat selection to AP Z-range.")
            # We can't easily force the selector UI to change shape instantly mid-drag, 
            # but we can override the stored box.
            # Better UX: Draw lines to tell user where to draw.
            # Upon release, we snap the stored box.
            z_min_curr = z_min_lock
            z_max_curr = z_max_lock
            # Optional: visual snap could be managed by setting extents, but tricky.
        else:
            self.update_z_lines(z_min_curr, z_max_curr, source='lat')

        self.lat_box = (y_min, y_max, z_min_curr, z_max_curr)
        print(f"Lat Box (Y={y_min:.1f}-{y_max:.1f}, Z={z_min_curr:.1f}-{z_max_curr:.1f})")

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
            x_min, x_max, z_min, z_max = self.ap_box
            cx = (x_min + x_max) / 2
            cz = (z_min + z_max) / 2
            
        # Lat Box gives Y and Z
        if self.lat_box:
            y_min, y_max, z_min_lat, z_max_lat = self.lat_box
            cy = (y_min + y_max) / 2
            if self.ap_box:
                # Z is already defined by AP box (primary), taking it is safer if we implement locking.
                # Or average. Since we are locking, they should be identical.
                pass 
            else:
                 cz = (z_min_lat + z_max_lat) / 2
        
        print(f"Calculated Center: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}")
        self.show_mprs_in_window((cx, cy, cz))

    def show_mprs_in_window(self, center):
        cx, cy, cz = int(center[0]), int(center[1]), int(center[2])
        
        # Clamp coordinates
        cx = max(0, min(cx, self.data.shape[0]-1))
        cy = max(0, min(cy, self.data.shape[1]-1))
        cz = max(0, min(cz, self.data.shape[2]-1))
        
        # Axial (Z=constant)
        if 0 <= cz < self.data.shape[2]:
            self.ax_axial.clear()
            ax_img = self.data[:, :, cz].T
            self.ax_axial.imshow(ax_img, cmap='gray', origin='lower', aspect=self.aspect_axial)
            self.ax_axial.set_title(f'Axial (Z={cz})')
            self.ax_axial.set_xlabel('X')
            self.ax_axial.set_ylabel('Y')
            self.ax_axial.axvline(cx, color='r', linewidth=0.8)
            self.ax_axial.axhline(cy, color='r', linewidth=0.8)
            
        # Coronal (Y=constant)
        if 0 <= cy < self.data.shape[1]:
            self.ax_coronal.clear()
            cor_img = self.data[:, cy, :].T
            self.ax_coronal.imshow(cor_img, cmap='gray', origin='lower', aspect=self.aspect_ap)
            self.ax_coronal.set_title(f'Coronal (Y={cy})')
            self.ax_coronal.set_xlabel('X')
            self.ax_coronal.set_ylabel('Z')
            self.ax_coronal.axvline(cx, color='r', linewidth=0.8)
            self.ax_coronal.axhline(cz, color='r', linewidth=0.8)
            
        # Sagittal (X=constant)
        if 0 <= cx < self.data.shape[0]:
            self.ax_sagittal.clear()
            sag_img = self.data[cx, :, :].T
            self.ax_sagittal.imshow(sag_img, cmap='gray', origin='lower', aspect=self.aspect_lat)
            self.ax_sagittal.set_title(f'Sagittal (X={cx})')
            self.ax_sagittal.set_xlabel('Y')
            self.ax_sagittal.set_ylabel('Z')
            self.ax_sagittal.axvline(cy, color='r', linewidth=0.8)
            self.ax_sagittal.axhline(cz, color='r', linewidth=0.8)
            
        self.fig.canvas.draw_idle()

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
