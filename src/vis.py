import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import RectangleSelector, Button
from matplotlib.patches import Rectangle
import matplotlib.gridspec as gridspec

class InteractiveAnnotator:
    def __init__(self, volume):
        self.volume = volume
        # Volume shape: (X, Y, Z)
        # AP Projection: Collapse Y -> (X, Z). Transpose for (Z, X) display (Z is vertical).
        self.ap_img = np.mean(volume, axis=1).T
        # Lateral Projection: Collapse X -> (Y, Z). Transpose for (Z, Y) display.
        self.lat_img = np.mean(volume, axis=0).T
        
        # Store selections: (x_start, y_start, x_end, y_end) in axes coords
        # Note: In plotting (Z, X), x-axis is X, y-axis is Z.
        # So selection will be (x_min, z_min, x_max, z_max).
        self.sel_ap = None 
        self.sel_lat = None
        
        self.fig = plt.figure(figsize=(12, 6))
        gs = gridspec.GridSpec(1, 3, width_ratios=[1, 1, 0.2])
        
        self.ax_ap = self.fig.add_subplot(gs[0])
        self.ax_ap.set_title("AP (Z vs X)")
        self.ax_ap.imshow(self.ap_img, cmap='gray', origin='lower', aspect='auto')
        self.ax_ap.set_xlabel("X (Right-Left)")
        self.ax_ap.set_ylabel("Z (Head-Foot)")
        
        self.ax_lat = self.fig.add_subplot(gs[1], sharey=self.ax_ap)
        self.ax_lat.set_title("Lateral (Z vs Y)")
        self.ax_lat.imshow(self.lat_img, cmap='gray', origin='lower', aspect='auto')
        self.ax_lat.set_xlabel("Y (Ant-Post)")
        # Share Y axis (Z physically)
        
        # Selectors
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
        
        # Button
        self.ax_btn = self.fig.add_subplot(gs[2])
        self.btn = Button(self.ax_btn, 'Confirm')
        self.btn.on_clicked(self.confirm)
        
        plt.show()

    def on_select_ap(self, eclick, erelease):
        # eclick and erelease are matplotlib events
        # Extent is (xmin, xmax, ymin, ymax)
        self.sel_ap = self.rs_ap.extents
        print(f"AP selection: {self.sel_ap}")

    def on_select_lat(self, eclick, erelease):
        self.sel_lat = self.rs_lat.extents
        print(f"Lat selection: {self.sel_lat}")

    def confirm(self, event):
        if self.sel_ap is None or self.sel_lat is None:
            print("Please draw bounding boxes on both views!")
            return
        
        # sel_ap: (x_min, x_max, z_min, z_max)  (Note: plot X is data X, plot Y is data Z)
        # sel_lat: (y_min, y_max, z_min, z_max) (Note: plot X is data Y, plot Y is data Z)
        
        x_min, x_max, z_min_ap, z_max_ap = self.sel_ap
        y_min, y_max, z_min_lat, z_max_lat = self.sel_lat
        
        # Combine Z (intersection)
        z_min = max(z_min_ap, z_min_lat)
        z_max = min(z_max_ap, z_max_lat)
        
        if z_min >= z_max:
            print("Z ranges do not overlap!")
            return
        
        bbox_3d = {
            'x': (int(x_min), int(x_max)),
            'y': (int(y_min), int(y_max)),
            'z': (int(z_min), int(z_max))
        }
        
        print(f"Confirmed BBox: {bbox_3d}")
        self.show_mpr(bbox_3d)

    def show_mpr(self, bbox):
        # Create MPR visualization
        # Center of bbox
        cx = int((bbox['x'][0] + bbox['x'][1]) / 2)
        cy = int((bbox['y'][0] + bbox['y'][1]) / 2)
        cz = int((bbox['z'][0] + bbox['z'][1]) / 2)
        
        # Clamp to volume dims
        cx = np.clip(cx, 0, self.volume.shape[0]-1)
        cy = np.clip(cy, 0, self.volume.shape[1]-1)
        cz = np.clip(cz, 0, self.volume.shape[2]-1)
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        
        # Axial (XY) - Slice Z
        axes[0].imshow(self.volume[:, :, cz].T, cmap='gray', origin='lower')
        axes[0].set_title(f"Axial (Z={cz})")
        # Draw Rect: x, y
        rect_ax = Rectangle((bbox['x'][0], bbox['y'][0]), 
                            bbox['x'][1]-bbox['x'][0], 
                            bbox['y'][1]-bbox['y'][0], 
                            edgecolor='r', facecolor='none')
        axes[0].add_patch(rect_ax)
        
        # Coronal (XZ) - Slice Y
        axes[1].imshow(self.volume[:, cy, :].T, cmap='gray', origin='lower')
        axes[1].set_title(f"Coronal (Y={cy})")
        # Draw Rect: x, z
        rect_cor = Rectangle((bbox['x'][0], bbox['z'][0]), 
                             bbox['x'][1]-bbox['x'][0], 
                             bbox['z'][1]-bbox['z'][0], 
                             edgecolor='r', facecolor='none')
        axes[1].add_patch(rect_cor)
        
        # Sagittal (YZ) - Slice X
        axes[2].imshow(self.volume[cx, :, :].T, cmap='gray', origin='lower')
        axes[2].set_title(f"Sagittal (X={cx})")
        # Draw Rect: y, z
        rect_sag = Rectangle((bbox['y'][0], bbox['z'][0]), 
                             bbox['y'][1]-bbox['y'][0], 
                             bbox['z'][1]-bbox['z'][0], 
                             edgecolor='r', facecolor='none')
        axes[2].add_patch(rect_sag)
        
        plt.show()
