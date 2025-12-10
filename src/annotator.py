import os
import sys
import csv
import time
import numpy as np
import nibabel as nib
import tkinter as tk
from tkinter import ttk, messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.widgets import RectangleSelector
from matplotlib.patches import Rectangle
import matplotlib.gridspec as gridspec

# --- Constants ---
LANDMARKS = [
    "1. Skull (Cranial Vault)",
    "2. Right Humeral Head (shoulder)",
    "3. Left Humeral Head (shoulder)",
    "4. Right Scapula",
    "5. Left Scapula",
    "6. Right Humeroulnar Joint (elbow)",
    "7. Left Humeroulnar Joint (elbow)",
    "8. Right Radiocarpal Joint (wrist)",
    "9. Left Radiocarpal Joint (wrist)",
    "10. T1 Vertebral Body",
    "11. Carina",
    "12. Right Hemidiaphragm",
    "13. Left Hemidiaphragm",
    "14. T12 Vertebral Body"
]
HU_SCALES = {
    "Default": -1000,
    "Bone (Soft)": 150, 
    "Bone (Hard)": 350
}
OUTPUT_CSV = "annotations.csv"

class TkAnnotator:
    def __init__(self, root, data_dir):
        self.root = root
        self.root.title("3D CT Annotator")
        self.root.geometry("1600x900")
        
        self.data_dir = data_dir
        self.file_list = [f for f in os.listdir(data_dir) if f.endswith('.nii.gz')]
        if not self.file_list:
            messagebox.showerror("Error", "No .nii.gz files found in data directory.")
            sys.exit(1)
            
        # State
        self.case_index = 0
        self.current_landmark_idx = 0
        self.resident_name = tk.StringVar(value="")
        self.case_id_search = tk.StringVar()
        
        # Data Placeholders
        self.img = None
        self.data = None
        self.raw_data = None
        self.voxel_sizes = None
        self.case_id = ""
        self.ap_view = None
        self.lat_view = None
        self.hu_scale = "Default"
        
        # Annotation State
        self.ap_box = None
        self.lat_box = None
        self.rect_ap_patch = None
        self.rect_lat_patch = None
        self.last_draw_time = 0
        self.is_submitted = False
        
        # --- UI Setup ---
        self.setup_theme() # NEW: Theme setup
        self.setup_layout()
        self.setup_controls()
        self.setup_canvas()
        
        # Load First Case
        self.load_case(0)

    def setup_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # 1. Larger Fonts & Aesthetics
        default_font = ("Segoe UI", 11)
        header_font = ("Segoe UI", 12, "bold")
        big_label_font = ("Segoe UI", 14, "bold")
        
        style.configure(".", font=default_font)
        style.configure("TLabel", font=default_font)
        style.configure("TButton", font=default_font, padding=5)
        style.configure("TLabelFrame.Label", font=header_font, foreground="#007ACC")
        style.configure("Big.TLabel", font=big_label_font, foreground="blue")

    def setup_layout(self):
        # Main Container
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # Left Panel (Controls) - Increased width for bigger fonts
        self.frame_controls = ttk.Frame(self.paned, padding=15, width=350) 
        self.paned.add(self.frame_controls, weight=0)
        
        # Right Panel (Canvas)
        self.frame_canvas = ttk.Frame(self.paned, padding=5)
        self.paned.add(self.frame_canvas, weight=1)

    def setup_controls(self):
        # 2. Prominent Current Landmark Display
        self.lbl_current_lm = ttk.Label(self.frame_controls, text="Initial Landmark", style="Big.TLabel", wraplength=330)
        self.lbl_current_lm.pack(fill=tk.X, pady=(0, 20))
        
        # User Info
        info_group = ttk.LabelFrame(self.frame_controls, text="User Info", padding=10)
        info_group.pack(fill=tk.X, pady=10)
        
        ttk.Label(info_group, text="Resident Full Name:").pack(anchor=tk.W)
        self.ent_name = ttk.Entry(info_group, textvariable=self.resident_name)
        self.ent_name.pack(fill=tk.X, pady=5)
        
        # Navigation
        nav_group = ttk.LabelFrame(self.frame_controls, text="Patient Navigation", padding=10)
        nav_group.pack(fill=tk.X, pady=10)
        
        case_frame = ttk.Frame(nav_group)
        case_frame.pack(fill=tk.X, pady=5)
        ttk.Button(case_frame, text="< Prev Case", command=self.prev_case).pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.lbl_case_idx = ttk.Label(case_frame, text="0/0")
        self.lbl_case_idx.pack(side=tk.LEFT, padx=10)
        ttk.Button(case_frame, text="Next Case >", command=self.next_case).pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        # Search
        search_frame = ttk.Frame(nav_group)
        search_frame.pack(fill=tk.X, pady=5)
        ttk.Entry(search_frame, textvariable=self.case_id_search).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(search_frame, text="Go", command=self.goto_case, width=5).pack(side=tk.LEFT, padx=5)

        # HU Scale
        win_group = ttk.LabelFrame(self.frame_controls, text="CT HU Scale", padding=10)
        win_group.pack(fill=tk.X, pady=10)
        self.cb_windowing = ttk.Combobox(win_group, values=list(HU_SCALES.keys()), state="readonly")
        self.cb_windowing.current(0)
        self.cb_windowing.bind("<<ComboboxSelected>>", self.on_scale_change)
        self.cb_windowing.pack(fill=tk.X)
        
        # 3. Landmark Selection & Navigation
        annot_group = ttk.LabelFrame(self.frame_controls, text="Landmark Selection", padding=10)
        annot_group.pack(fill=tk.X, pady=10)
        
        # Next/Prev Landmark Buttons
        lm_nav_frame = ttk.Frame(annot_group)
        lm_nav_frame.pack(fill=tk.X, pady=5)
        ttk.Button(lm_nav_frame, text="< Prev LM", command=self.prev_landmark).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(lm_nav_frame, text="Next LM >", command=self.next_landmark).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.cb_landmarks = ttk.Combobox(annot_group, values=LANDMARKS, state="readonly")
        self.cb_landmarks.current(0)
        self.cb_landmarks.bind("<<ComboboxSelected>>", self.on_landmark_change)
        self.cb_landmarks.pack(fill=tk.X, pady=10)
        
        # Current Selection Info
        self.lbl_coords = ttk.Label(self.frame_controls, text="Selection: None", font=("Consolas", 10), foreground="red")
        self.lbl_coords.pack(pady=5)
        
        # Actions
        action_group = ttk.Frame(self.frame_controls)
        action_group.pack(fill=tk.X, pady=20)
        
        ttk.Button(action_group, text="Visual Check (MPR)", command=self.visual_check).pack(fill=tk.X, pady=5)
        btn_submit = ttk.Button(action_group, text="Submit Annotation", command=self.submit_annotation)
        btn_submit.pack(fill=tk.X, pady=5)
        
        self.lbl_status = ttk.Label(self.frame_controls, text="", foreground="green")
        self.lbl_status.pack(pady=10)

    def setup_canvas(self):
        # Matplotlib Figure
        # 1 Row, 3 Cols (AP, Lat, MPR)
        self.fig = Figure(figsize=(15, 8), dpi=100)
        gs = gridspec.GridSpec(3, 3, width_ratios=[1, 1, 0.6])
        
        # AP View
        self.ax_ap = self.fig.add_subplot(gs[:, 0])
        self.ax_ap.set_title("AP View")
        
        # Lat View
        self.ax_lat = self.fig.add_subplot(gs[:, 1])
        self.ax_lat.set_title("Lateral View")
        
        # MPR Views
        self.ax_axial = self.fig.add_subplot(gs[0, 2])
        self.ax_axial.set_title("Axial")
        self.ax_coronal = self.fig.add_subplot(gs[1, 2])
        self.ax_coronal.set_title("Coronal")
        self.ax_sagittal = self.fig.add_subplot(gs[2, 2])
        self.ax_sagittal.set_title("Sagittal")
        
        self.fig.tight_layout()
        
        # Canvas Widget
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_canvas)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        # Z-Lines (Animated)
        self.z_line_lat = self.ax_lat.axhline(0, color='cyan', linestyle='-', linewidth=1, alpha=0, animated=True)
        self.z_line_ap = self.ax_ap.axhline(0, color='cyan', linestyle='-', linewidth=1, alpha=0, animated=True)
        
        # Blitting Backgrounds
        self.bg_ap = None
        self.bg_lat = None
        self.canvas.mpl_connect('draw_event', self.on_draw) 

        # Instructions Panel (Bottom)
        self.setup_instructions()

    def setup_instructions(self):
        # Styled Protocol Frame
        style = ttk.Style()
        style.configure("Instr.TLabel", font=("Segoe UI", 10), padding=2)
        
        instr_frame = ttk.LabelFrame(self.frame_canvas, text="Annotation Protocol", padding=(15, 10))
        instr_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))
        
        steps = [
            "1. Enter your Full Name (Resident).",
            "2. Locate current landmark on AP & Lateral views.",
            "3. Draw bounding boxes on BOTH views (Z-line is your guide).",
            "4. Verify using 'Visual Check' & adjust if needed.",
            "5. Click 'Next LM' to Auto-Save & Continue.",
            "6. Repeat for all landmarks, then click 'Next Case'.",
            "Note: Multiple submissions per landmark are accepted if corrections are needed."
        ]
        
        # Grid steps for a neat 2-column look if it fits, or just list them.
        # Let's do a flow layout using a single label for simplicity and alignment.
        full_text = "  |  ".join(steps[:3]) + "\n" + "  |  ".join(steps[3:6]) + "\n" + steps[6]
        
        # Alternatively, a clean vertical list is easier to read quickly
        lbl_text = "\n".join(steps)
        
        ttk.Label(instr_frame, text=lbl_text, style="Instr.TLabel", justify=tk.LEFT).pack(anchor=tk.W)

    # --- Logic ---

    def load_case(self, index):
        if index < 0 or index >= len(self.file_list): return
        
        self.case_index = index
        filename = self.file_list[index]
        self.case_id = filename.split('_')[0]
        self.case_id_search.set(self.case_id)
        
        path = os.path.join(self.data_dir, filename)
        print(f"Loading {filename}...")
        
        img = nib.load(path)
        img = nib.as_closest_canonical(img)
        self.raw_data = img.get_fdata() # Keep raw copy
        self.voxel_sizes = img.header.get_zooms()
        
        self.apply_hu_scale()
        
        self.lbl_case_idx.config(text=f"Case {self.case_index+1}/{len(self.file_list)}")
        
        # Initial Display
        self.on_landmark_change(None)

    def display_base_images(self):
        dx, dy, dz = self.voxel_sizes
        
        # AP
        self.ax_ap.clear()
        self.ax_ap.imshow(self.ap_view, cmap='gray', origin='lower')
        self.ax_ap.set_aspect(dz/dx)
        self.ax_ap.set_title("AP View")
        
        # Lat
        self.ax_lat.clear()
        self.ax_lat.imshow(self.lat_view, cmap='gray', origin='lower')
        self.ax_lat.set_aspect(dz/dy)
        self.ax_lat.set_title("Lateral View")
        
        # Selectors (Must recreate on clear)
        self.rs_ap = RectangleSelector(self.ax_ap, self.on_select_ap, useblit=True, button=[1], 
                                       minspanx=5, minspany=5, spancoords='pixels', interactive=True)
        self.rs_lat = RectangleSelector(self.ax_lat, self.on_select_lat, useblit=True, button=[1], 
                                       minspanx=5, minspany=5, spancoords='pixels', interactive=True)
        
        # Z-lines
        self.z_line_lat = self.ax_lat.axhline(0, color='cyan', linestyle='-', linewidth=1, alpha=0, animated=True)
        self.z_line_ap = self.ax_ap.axhline(0, color='cyan', linestyle='-', linewidth=1, alpha=0, animated=True)
        
        self.canvas.draw()


    # --- Callbacks ---
    def prev_case(self): 
        self.submit_annotation(silent=True) # Auto-save
        self.load_case(self.case_index - 1)

    def next_case(self): 
        self.submit_annotation(silent=True) # Auto-save
        self.load_case(self.case_index + 1)
    
    def goto_case(self):
        self.submit_annotation(silent=True)
        search = self.case_id_search.get().strip()
        for i, f in enumerate(self.file_list):
            if search in f:
                self.load_case(i)
                return
        messagebox.showinfo("Not Found", f"Case ID {search} not found.")

    def on_scale_change(self, event):
        self.hu_scale = self.cb_windowing.get()
        self.apply_hu_scale()
        
        self.display_base_images()
        
        if self.ap_box and self.lat_box:
           self.display_annotation(self.ap_box, self.lat_box)
        else:
           self.canvas.draw()
            
    def apply_hu_scale(self):
        # Filter data based on HU threshold
        threshold = HU_SCALES[self.hu_scale]
        
        # Create masked data (-1000 is air/black)
        # Note: This is a heavy operation
        self.data = np.where(self.raw_data < threshold, -1000, self.raw_data)
        
        # Recompute projections
        self.ap_view = np.mean(self.data, axis=1).T
        self.lat_view = np.mean(self.data, axis=0).T

    def prev_landmark(self):
        try:
            self.submit_annotation(silent=True)
        except Exception as e:
            print(f"Auto-save error: {e}")
        
        idx = (self.current_landmark_idx - 1) % len(LANDMARKS)
        self.cb_landmarks.current(idx)
        self.on_landmark_change(None)

    def next_landmark(self):
        try:
            self.submit_annotation(silent=True)
        except Exception as e:
            print(f"Auto-save error: {e}")
            
        idx = (self.current_landmark_idx + 1) % len(LANDMARKS)
        self.cb_landmarks.current(idx)
        self.on_landmark_change(None)

    def on_landmark_change(self, event):
        self.is_submitted = False
        self.current_landmark_idx = self.cb_landmarks.current()
        
        # Update Big Label
        lm_text = LANDMARKS[self.current_landmark_idx]
        self.lbl_current_lm.config(text=lm_text)
        
        # Try to load existing
        if not self.load_existing_annotation():
            self.clear_visuals()

    def clear_visuals(self):
        self.ap_box = None
        self.lat_box = None
        self.rect_ap_patch = None
        self.rect_lat_patch = None
        
        # Aggressive Reset: Redraw Base Images to wipe everything
        self.display_base_images()
        
        # Clear MPRs
        self.ax_axial.clear(); self.ax_axial.set_title("Axial")
        self.ax_coronal.clear(); self.ax_coronal.set_title("Coronal")
        self.ax_sagittal.clear(); self.ax_sagittal.set_title("Sagittal")
        self.canvas.draw()
        
        self.update_coords_label()

    def update_coords_label(self):
        coords = self.get_xyz()
        if coords:
            cx, cy, cz = coords
            self.lbl_coords.config(text=f"Sel: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}")
        else:
            self.lbl_coords.config(text="Sel: None (0, 0, 0)")

    # --- Drawing Logic ---
    def on_draw(self, event):
        if event is not None and event.canvas != self.canvas: return
        self.bg_ap = self.canvas.copy_from_bbox(self.ax_ap.bbox)
        self.bg_lat = self.canvas.copy_from_bbox(self.ax_lat.bbox)
        # Redraw patches if they exist + Z lines
        if self.rect_ap_patch: self.ax_ap.draw_artist(self.rect_ap_patch)
        if self.rect_lat_patch: self.ax_lat.draw_artist(self.rect_lat_patch)
        self.ax_ap.draw_artist(self.z_line_ap)
        self.ax_lat.draw_artist(self.z_line_lat)

    def on_select_ap(self, eclick, erelease):
        if time.time() - self.last_draw_time < 0.05: return
        self.last_draw_time = time.time()
        self.is_submitted = False
        
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        z_min, z_max = min(y1, y2), max(y1, y2)
        z_center = (z_min + z_max) / 2
        
        self.ap_box = (min(x1, x2), max(x1, x2), z_min, z_max)
        
        # 1. Create Persistent Patch on AP
        if self.rect_ap_patch: 
            try: self.rect_ap_patch.remove()
            except: pass
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        self.rect_ap_patch = Rectangle((min(x1, x2), min(y1, y2)), width, height, 
                                       linewidth=1, edgecolor='red', facecolor='none', animated=True)
        self.ax_ap.add_patch(self.rect_ap_patch)
        
        # 2. Update Lat Line
        self.z_line_lat.set_ydata([z_center]*2)
        self.z_line_lat.set_alpha(1) # Visible
        
        # 3. Blit AP (Show new box)
        self.canvas.restore_region(self.bg_ap)
        self.ax_ap.draw_artist(self.rect_ap_patch)
        self.ax_ap.draw_artist(self.z_line_ap) # Keep existing line
        self.canvas.blit(self.ax_ap.bbox)
        
        # 4. Blit Lat (Show new Line)
        self.canvas.restore_region(self.bg_lat)
        if self.rect_lat_patch: self.ax_lat.draw_artist(self.rect_lat_patch) # Keep existing box
        self.ax_lat.draw_artist(self.z_line_lat)
        self.canvas.blit(self.ax_lat.bbox)
        
        self.update_coords_label()

    def on_select_lat(self, eclick, erelease):
        if time.time() - self.last_draw_time < 0.05: return
        self.last_draw_time = time.time()
        self.is_submitted = False
        
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        z_min, z_max = min(y1, y2), max(y1, y2)
        z_center = (z_min + z_max) / 2
        
        self.lat_box = (min(x1, x2), max(x1, x2), z_min, z_max)
        
        # 1. Create Persistent Patch on Lat
        if self.rect_lat_patch:
            try: self.rect_lat_patch.remove()
            except: pass
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        self.rect_lat_patch = Rectangle((min(x1, x2), min(y1, y2)), width, height,
                                        linewidth=1, edgecolor='red', facecolor='none', animated=True)
        self.ax_lat.add_patch(self.rect_lat_patch)
        
        # 2. Update AP Line
        self.z_line_ap.set_ydata([z_center]*2)
        self.z_line_ap.set_alpha(1) # Visible
        
        # 3. Blit Lat (Show new box)
        self.canvas.restore_region(self.bg_lat)
        self.ax_lat.draw_artist(self.rect_lat_patch)
        self.ax_lat.draw_artist(self.z_line_lat)
        self.canvas.blit(self.ax_lat.bbox)
        
        # 4. Blit AP (Show new Line)
        self.canvas.restore_region(self.bg_ap)
        if self.rect_ap_patch: self.ax_ap.draw_artist(self.rect_ap_patch)
        self.ax_ap.draw_artist(self.z_line_ap)
        self.canvas.blit(self.ax_ap.bbox)
        
        self.update_coords_label()


    def get_xyz(self):
        if not self.ap_box or not self.lat_box: return None
        x_min, x_max, z_min_ap, z_max_ap = self.ap_box
        cx = (x_min + x_max) / 2
        y_min, y_max, z_min_lat, z_max_lat = self.lat_box
        cy = (y_min + y_max) / 2
        cz = ((z_min_ap + z_max_ap) / 2 + (z_min_lat + z_max_lat) / 2) / 2
        return cx, cy, cz

    # --- MPR ---
    def visual_check(self):
        coords = self.get_xyz()
        if not coords:
            messagebox.showwarning("Incomplete", "Draw boxes on both views first.")
            return

        cx, cy, cz = coords
        ix, iy, iz = int(cx), int(cy), int(cz)
        
        # Clamping
        ix = max(0, min(ix, self.data.shape[0]-1))
        iy = max(0, min(iy, self.data.shape[1]-1))
        iz = max(0, min(iz, self.data.shape[2]-1))
        
        dx, dy, dz = self.voxel_sizes
        
        # Axial (Data is already filtered by apply_hu_scale)
        self.ax_axial.clear()
        self.ax_axial.imshow(self.data[:, :, iz].T, cmap='gray', origin='lower')
        self.ax_axial.set_aspect(dy/dx)
        self.ax_axial.set_title(f"Axial (Z={iz})")
        self.ax_axial.axvline(ix, color='r', lw=0.8); self.ax_axial.axhline(iy, color='r', lw=0.8)
        
        # Coronal
        self.ax_coronal.clear()
        self.ax_coronal.imshow(self.data[:, iy, :].T, cmap='gray', origin='lower')
        self.ax_coronal.set_aspect(dz/dx)
        self.ax_coronal.set_title(f"Coronal (Y={iy})")
        self.ax_coronal.axvline(ix, color='r', lw=0.8); self.ax_coronal.axhline(iz, color='r', lw=0.8)
        
        # Sagittal
        self.ax_sagittal.clear()
        self.ax_sagittal.imshow(self.data[ix, :, :].T, cmap='gray', origin='lower')
        self.ax_sagittal.set_aspect(dz/dy)
        self.ax_sagittal.set_title(f"Sagittal (X={ix})")
        self.ax_sagittal.axvline(iy, color='r', lw=0.8); self.ax_sagittal.axhline(iz, color='r', lw=0.8)
        
        self.canvas.draw()

    def submit_annotation(self, silent=False):
        name = self.resident_name.get().strip()
        if not silent and not name:
            messagebox.showwarning("Missing Info", "Please enter Resident Name.")
            return
        if silent and not name: return # Can't save without name
            
        coords = self.get_xyz()
        if not silent and not coords:
            messagebox.showwarning("Incomplete", "Draw bounding boxes first.")
            return
        if silent and not coords: return # Nothing to save
        
        # Prevent Double Save
        if self.is_submitted:
            if silent: return # Skip auto-save if already submitted
            # If manual submit, we can just say "Already saved" or update anyway?
            # User might want to force re-save? 
            # Protocol: If user modifies, is_submitted is False. 
            # So if is_submitted is True, they haven't touched it.
            if not silent:
                self.lbl_status.config(text=f"Already saved {LANDMARKS[self.current_landmark_idx].split('. ')[1]}!")
                return
            
        cx, cy, cz = coords
        lm_str = LANDMARKS[self.current_landmark_idx]
        lm_idx = lm_str.split('.')[0]
        lm_name = lm_str.split('. ')[1]
        
        # Format Box Strings (x1;x2;z1;z2)
        ap_str = f"{self.ap_box[0]:.1f};{self.ap_box[1]:.1f};{self.ap_box[2]:.1f};{self.ap_box[3]:.1f}"
        lat_str = f"{self.lat_box[0]:.1f};{self.lat_box[1]:.1f};{self.lat_box[2]:.1f};{self.lat_box[3]:.1f}"
        
        row = [
            self.case_id,
            os.path.basename(self.file_list[self.case_index]),
            name,
            lm_idx,
            lm_name,
            f"{cx:.2f}",
            f"{cy:.2f}",
            f"{cz:.2f}",
            ap_str,
            lat_str
        ]
        
        try:
            write_header = not os.path.exists(OUTPUT_CSV)
            with open(OUTPUT_CSV, 'a', newline='') as f:
                writer = csv.writer(f)
                if write_header:
                    writer.writerow(['CaseID', 'FileName', 'Resident', 'LandmarkIdx', 'LandmarkName', 'X', 'Y', 'Z', 'AP_Box', 'Lat_Box'])
                writer.writerow(row)
            
            if not silent:
                self.lbl_status.config(text=f"Saved {lm_name}!")
            else:
                self.lbl_status.config(text=f"Auto-saved {lm_name}!")
            
            self.is_submitted = True
            
        except PermissionError:
            if not silent: messagebox.showerror("Error", "CSV file is open. Close it and retry.")

    def load_existing_annotation(self):
        if not os.path.exists(OUTPUT_CSV): return False
        
        name = self.resident_name.get().strip()
        if not name: return False
        
        lm_idx = LANDMARKS[self.current_landmark_idx].split('.')[0]
        target_row = None
        
        try:
            with open(OUTPUT_CSV, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header: return False
                
                # Search for latest entry matching Case, Resident, Landmark
                for row in reader:
                    if len(row) < 10: continue
                    # Row: CaseID, FileName, Resident, LandmarkIdx, LandmarkName, X, Y, Z, AP_Box, Lat_Box
                    r_case, _, r_name, r_lm_idx = row[0], row[1], row[2], row[3]
                    
                    if r_case == self.case_id and r_name == name and r_lm_idx == lm_idx:
                        target_row = row
            
            if target_row:
                # Parse Boxes
                # Format: x1;x2;z1;z2
                ap_parts = [float(x) for x in target_row[8].split(';')]
                lat_parts = [float(x) for x in target_row[9].split(';')]
                
                ap_box = (ap_parts[0], ap_parts[1], ap_parts[2], ap_parts[3])
                lat_box = (lat_parts[0], lat_parts[1], lat_parts[2], lat_parts[3])
                
                self.display_annotation(ap_box, lat_box)
                self.lbl_status.config(text=f"Loaded existing: {target_row[4]}")
                return True
                
        except Exception as e:
            print(f"Error loading annotation: {e}")
            
        return False

    def display_annotation(self, ap_box, lat_box):
        self.clear_visuals() # Clear first, then draw new
        
        self.ap_box = ap_box
        self.lat_box = lat_box
        
        # Recreate visual elements
        # AP Patch
        x1, x2, z_min, z_max = ap_box
        width = abs(x2 - x1)
        height = abs(z_max - z_min)
        self.rect_ap_patch = Rectangle((min(x1, x2), min(z_min, z_max)), width, height, 
                                       linewidth=1, edgecolor='red', facecolor='none', animated=True)
        self.ax_ap.add_patch(self.rect_ap_patch)
        
        # Lat Patch
        x1_l, x2_l, z_min_l, z_max_l = lat_box
        width_l = abs(x2_l - x1_l)
        height_l = abs(z_max_l - z_min_l)
        self.rect_lat_patch = Rectangle((min(x1_l, x2_l), min(z_min_l, z_max_l)), width_l, height_l,
                                        linewidth=1, edgecolor='red', facecolor='none', animated=True)
        self.ax_lat.add_patch(self.rect_lat_patch)
        
        # Z-Lines
        z_center = (z_min + z_max) / 2 # Using AP Z for consistency, they should align
        self.z_line_lat.set_ydata([z_center]*2)
        self.z_line_lat.set_alpha(1)
        
        self.z_line_ap.set_ydata([z_center]*2)
        self.z_line_ap.set_alpha(1)
        
        self.canvas.draw()
        self.is_submitted = True # Mark as "clean"
        self.update_coords_label()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    if not os.path.exists(data_dir): os.makedirs(data_dir, exist_ok=True)
    
    root = tk.Tk()
    # Use a nice theme if available
    style = ttk.Style()
    if 'clam' in style.theme_names():
        style.theme_use('clam')
        
    app = TkAnnotator(root, data_dir)
    
    if args.test:
        print("Setup GUI complete in test mode.")
        root.update()
        root.destroy()
    else:
        root.mainloop()
