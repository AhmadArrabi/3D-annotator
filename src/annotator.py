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

# --- Login Dialog ---
class LoginDialog:
    def __init__(self, parent):
        self.parent = parent
        self.result_name = None
        
        # Setup Window
        self.top = tk.Toplevel(parent)
        self.top.title("Welcome - 3D CT Annotator Study")
        self.top.geometry("600x600")
        self.top.resizable(True, True)
        self.top.lift()
        self.top.focus_force()
        # Modality handled by wait_window

        # Styling
        style = ttk.Style()
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Body.TLabel", font=("Segoe UI", 11))
        
        # Content
        ttk.Label(self.top, text="3D CT Annotation Study", style="Title.TLabel").pack(pady=20)
        
        info_text = (
            "Thank you for participating in this study.\n\n"
            "Goal: To create a high-quality dataset of anatomical landmarks.\n\n"
            "Instructions:\n"
            "1. You will be presented with a series of CT cases.\n"
            "2. For each case, locate the requested landmarks.\n"
            "3. Draw bounding boxes on the AP and Lateral views.\n"
            "4. Use the MPR views to refine your selection.\n"
            "5. Press 'Next' to save and proceed."
        )
        lbl_info = ttk.Label(self.top, text=info_text, style="Body.TLabel", wraplength=450, justify="left")
        lbl_info.pack(pady=10, padx=20)
        
        # Input
        input_frame = ttk.Frame(self.top)
        input_frame.pack(pady=30, fill=tk.X, padx=50)
        
        ttk.Label(input_frame, text="Please enter your Full Name:", style="Body.TLabel").pack(anchor=tk.W)
        self.ent_name = ttk.Entry(input_frame, font=("Segoe UI", 16))
        self.ent_name.pack(fill=tk.X, pady=10, ipady=5)
        self.ent_name.bind("<Return>", self.on_submit)
        
        # Submit
        btn_start = ttk.Button(self.top, text="Start Annotation", command=self.on_submit, width=20)
        btn_start.pack(pady=10)
        
        # Protocol to handle 'X' close
        self.top.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Wait
        self.parent.wait_window(self.top)

    def on_submit(self, event=None):
        name = self.ent_name.get().strip()
        if not name:
            messagebox.showwarning("Required", "Please enter your name to proceed.")
            return
        self.result_name = name
        self.top.destroy()
        
    def on_close(self):
        self.top.destroy()


class TkAnnotator:
    def __init__(self, root, data_dir, resident_name):
        self.root = root
        self.root.title("3D CT Annotator")
        self.root.state("zoomed") # Maximized window
        
        self.data_dir = data_dir
        self.file_list = sorted([f for f in os.listdir(data_dir) if f.endswith('.nii.gz')])
        if not self.file_list:
            messagebox.showerror("Error", "No .nii.gz files found in data directory!")
            sys.exit(1)
            
        # State
        self.case_index = 0
        self.resident_name = tk.StringVar(value=resident_name)
        self.case_id_search = tk.StringVar()
        
        self.current_landmark_idx = 0
        self.is_submitted = False
        self.hu_scale = "Default"
        
        # Annotation State
        self.box_3d = None # [x1, x2, y1, y2, z1, z2]
        
        # Visual Elements State
        self.rect_ap = None
        self.rect_lat = None
        self.rect_axial = None
        self.rect_coronal = None
        self.rect_sagittal = None
        
        self.setup_theme()
        self.setup_layout()
        self.setup_controls()
        self.setup_canvas()
        
        # Load first case
        self.load_case(0)

    def setup_theme(self):
        style = ttk.Style()
        style.theme_use('clam')
        
        # Modern Palette
        BG_COLOR = "#f0f0f0"
        ACCENT_COLOR = "#0078d7"
        
        style.configure(".", background=BG_COLOR, font=("Segoe UI", 10))
        style.configure("TLabel", background=BG_COLOR)
        style.configure("TButton", padding=6, relief="flat", background="#e1e1e1")
        style.map("TButton", background=[("active", "#cce4f7")])
        style.configure("Big.TLabel", font=("Segoe UI", 14, "bold"), foreground=ACCENT_COLOR)

    def setup_layout(self):
        # Main container
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Paned Window (Left Controls, Right Canvas)
        self.paned = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)
        
        # 1. Controls Panel
        self.frame_controls = ttk.Frame(self.paned, padding=20, width=350)
        self.paned.add(self.frame_controls, weight=0) # Fixed width
        
        # 2. Canvas Panel
        self.frame_canvas = ttk.Frame(self.paned, padding=5)
        self.paned.add(self.frame_canvas, weight=1)

    def setup_controls(self):
        # Greeting
        greeting = f"Hi, {self.resident_name.get()}"
        ttk.Label(self.frame_controls, text=greeting, font=("Segoe UI", 12, "bold"), foreground="gray").pack(anchor=tk.W, pady=(0, 10))

        # 2. Prominent Current Landmark Display
        self.lbl_current_lm = ttk.Label(self.frame_controls, text="Initial Landmark", style="Big.TLabel", wraplength=330)
        self.lbl_current_lm.pack(fill=tk.X, pady=(0, 20))
        
        # User Info Removed (Handled by Login)
        
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
        
        # Trigger removed: Visual Check is now automatic
        btn_submit = ttk.Button(action_group, text="Submit Annotation", command=self.submit_annotation)
        btn_submit.pack(fill=tk.X, pady=5)
        
        self.lbl_status = ttk.Label(self.frame_controls, text="", foreground="green")
        self.lbl_status.pack(pady=10)

    def setup_canvas(self):
        # Matplotlib Figure
        # 2 Rows: Top (AP, Lat), Bottom (MPRs)
        self.fig = Figure(figsize=(15, 9), dpi=100)
        # Maximize space: small margins
        self.fig.subplots_adjust(left=0.005, right=0.995, top=0.96, bottom=0.005)
        
        # Grid: hspace/wspace minimized
        gs = gridspec.GridSpec(2, 6, height_ratios=[1.5, 1], hspace=0.15, wspace=0.05)
        
        # AP View (Top Left)
        self.ax_ap = self.fig.add_subplot(gs[0, 0:3])
        self.ax_ap.set_title("AP View (X-Z)")
        
        # Lat View (Top Right)
        self.ax_lat = self.fig.add_subplot(gs[0, 3:6])
        self.ax_lat.set_title("Lateral View (Y-Z)")
        
        # MPR Views (Bottom Row)
        self.ax_axial = self.fig.add_subplot(gs[1, 0:2])
        self.ax_axial.set_title("Axial (X-Y)")
        self.ax_coronal = self.fig.add_subplot(gs[1, 2:4])
        self.ax_coronal.set_title("Coronal (X-Z)")
        self.ax_sagittal = self.fig.add_subplot(gs[1, 4:6])
        self.ax_sagittal.set_title("Sagittal (Y-Z)")
        
        # Overlay Instructions Panel (Use place instead of pack)
        self.setup_instructions_overlay()

        # Canvas Widget
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.frame_canvas)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        
        self.canvas.mpl_connect('draw_event', self.on_draw) 

    def setup_instructions_overlay(self):
        # Styled Protocol Frame
        style = ttk.Style()
        style.configure("Instr.TLabel", font=("Segoe UI", 10), padding=2, background="white")
        style.configure("Instr.TLabelframe", background="white")
        style.configure("Instr.TLabelframe.Label", background="white", font=("Segoe UI", 10, "bold"))
        
        self.instr_frame = ttk.LabelFrame(self.frame_canvas, text="Protocol", style="Instr.TLabelframe", padding=(10, 5))
        
        # Place at bottom left of canvas frame, floating
        self.instr_frame.place(relx=0.01, rely=0.99, anchor="sw")
        
        steps = [
            "1. Resident Name",
            "2. Draw on AP/Lat",
            "3. Refine on MPR",
            "4. Next LM"
        ]
        lbl_text = " | ".join(steps)
        ttk.Label(self.instr_frame, text=lbl_text, style="Instr.TLabel").pack()

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
        
        # If box exists, refresh MPRs with new HU scaling
        if self.box_3d:
           self.visual_check()
        else:
           # If no box, ensure MPRs are cleared (in case they had content)
           self.ax_axial.clear(); self.ax_axial.set_title("Axial (X-Y)")
           self.ax_coronal.clear(); self.ax_coronal.set_title("Coronal (X-Z)")
           self.ax_sagittal.clear(); self.ax_sagittal.set_title("Sagittal (Y-Z)")
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

    def display_base_images(self):
        dx, dy, dz = self.voxel_sizes
        
        # Helper to setup view
        def setup_view(ax, data, aspect, title, callback):
            ax.clear()
            ax.imshow(data, cmap='gray', origin='lower')
            ax.set_aspect(aspect)
            ax.set_title(title)
            return RectangleSelector(ax, callback, useblit=True, button=[1], 
                                     minspanx=5, minspany=5, spancoords='pixels', interactive=False)
        
        # 1. AP (X-Z)
        self.rs_ap = setup_view(self.ax_ap, self.ap_view, dz/dx, "AP View (X-Z)", self.on_select_ap)
        
        # 2. Lat (Y-Z)
        self.rs_lat = setup_view(self.ax_lat, self.lat_view, dz/dy, "Lateral View (Y-Z)", self.on_select_lat)
        
        # MPR Setup removed: Initially empty until box selected
        
        self.canvas.draw()
        
        # If we have existing annotation, show it (and generate MPRs)
        if self.box_3d:
            self.visual_check()

    def clear_visuals(self):
        self.box_3d = None
        self.rect_ap = None; self.rect_lat = None
        self.rect_axial = None; self.rect_coronal = None; self.rect_sagittal = None
        
        # Explicit clear of MPR views
        self.ax_axial.clear(); self.ax_axial.set_title("Axial (X-Y)")
        self.ax_coronal.clear(); self.ax_coronal.set_title("Coronal (X-Z)")
        self.ax_sagittal.clear(); self.ax_sagittal.set_title("Sagittal (Y-Z)")
        
        self.display_base_images()
        self.update_coords_label()

    def update_coords_label(self):
        if self.box_3d:
            x1, x2, y1, y2, z1, z2 = self.box_3d
            cx, cy, cz = (x1+x2)/2, (y1+y2)/2, (z1+z2)/2
            self.lbl_coords.config(text=f"Sel: X={cx:.1f}, Y={cy:.1f}, Z={cz:.1f}")
        else:
            self.lbl_coords.config(text="Sel: None")

    # --- Drawing Logic ---
    def on_draw(self, event):
        if event is not None and event.canvas != self.canvas: return
        # Simple full redraw for now to ensure stability with 5 views
        # Blitting 5 views is complex to manage perfect background restores
        pass 

    def update_box_from_view(self, view_name, dim_indices, values):
        """
        view_name: str
        dim_indices: list of indices in box_3d [x1, x2, y1, y2, z1, z2] to update
        values: list of new values corresponding to dim_indices
        """
        if not self.box_3d:
            # Initialize with whole volume or sensible default if starting from MPR? 
            # Usually start from AP/Lat. If starting MPR, valid other dims are needed.
            # providing defaults from volume center if needed.
            nx, ny, nz = self.data.shape
            self.box_3d = [0, nx, 0, ny, 0, nz]
            
        for idx, val in zip(dim_indices, values):
            self.box_3d[idx] = val
            
        self.visual_check()
        self.is_submitted = False
        self.update_coords_label()

    # Selectors
    def on_select_ap(self, eclick, erelease):
        x1, z1 = eclick.xdata, eclick.ydata
        x2, z2 = erelease.xdata, erelease.ydata
        self.update_box_from_view("AP", [0, 1, 4, 5], [min(x1, x2), max(x1, x2), min(z1, z2), max(z1, z2)])

    def on_select_lat(self, eclick, erelease):
        y1, z1 = eclick.xdata, eclick.ydata
        y2, z2 = erelease.xdata, erelease.ydata
        self.update_box_from_view("Lat", [2, 3, 4, 5], [min(y1, y2), max(y1, y2), min(z1, z2), max(z1, z2)])

    def on_select_axial(self, eclick, erelease):
        x1, y1 = eclick.xdata, eclick.ydata
        x2, y2 = erelease.xdata, erelease.ydata
        self.update_box_from_view("Axial", [0, 1, 2, 3], [min(x1, x2), max(x1, x2), min(y1, y2), max(y1, y2)])
        
    def on_select_coronal(self, eclick, erelease):
        x1, z1 = eclick.xdata, eclick.ydata
        x2, z2 = erelease.xdata, erelease.ydata
        self.update_box_from_view("Coronal", [0, 1, 4, 5], [min(x1, x2), max(x1, x2), min(z1, z2), max(z1, z2)])
        
    def on_select_sagittal(self, eclick, erelease):
        y1, z1 = eclick.xdata, eclick.ydata
        y2, z2 = erelease.xdata, erelease.ydata
        self.update_box_from_view("Sagittal", [2, 3, 4, 5], [min(y1, y2), max(y1, y2), min(z1, z2), max(z1, z2)])

    def get_xyz(self):
        if not self.box_3d: return None
        x1, x2, y1, y2, z1, z2 = self.box_3d
        return (x1+x2)/2, (y1+y2)/2, (z1+z2)/2

    # --- MPR ---
    def visual_check(self):
        # Just forces a redraw of the MPR slices based on current center
        if not self.box_3d:
            return

        x1, x2, y1, y2, z1, z2 = self.box_3d
        cx, cy, cz = (x1+x2)/2, (y1+y2)/2, (z1+z2)/2
        
        ix, iy, iz = int(cx), int(cy), int(cz)
        
        # Clamping
        ix = max(0, min(ix, self.data.shape[0]-1))
        iy = max(0, min(iy, self.data.shape[1]-1))
        iz = max(0, min(iz, self.data.shape[2]-1))
        
        dx, dy, dz = self.voxel_sizes
        
        # Helper for display
        def show_slice(ax, data, aspect, title):
            ax.clear()
            ax.imshow(data, cmap='gray', origin='lower')
            ax.set_aspect(aspect)
            ax.set_title(title)
            
        # Axial (XY)
        show_slice(self.ax_axial, self.data[:, :, iz].T, dy/dx, f"Axial (Z={iz})")
        self.rs_axial = RectangleSelector(self.ax_axial, self.on_select_axial, useblit=True, button=[1], 
                                          minspanx=5, minspany=5, spancoords='pixels', interactive=False)
                                          
        # Coronal (XZ)
        show_slice(self.ax_coronal, self.data[:, iy, :].T, dz/dx, f"Coronal (Y={iy})")
        self.rs_coronal = RectangleSelector(self.ax_coronal, self.on_select_coronal, useblit=True, button=[1], 
                                            minspanx=5, minspany=5, spancoords='pixels', interactive=False)
                                            
        # Sagittal (YZ)
        show_slice(self.ax_sagittal, self.data[ix, :, :].T, dz/dy, f"Sagittal (X={ix})")
        self.rs_sagittal = RectangleSelector(self.ax_sagittal, self.on_select_sagittal, useblit=True, button=[1], 
                                             minspanx=5, minspany=5, spancoords='pixels', interactive=False)
        
        # Draw the boxes on top of new slices
        self.display_annotation()

    def submit_annotation(self, silent=False):
        name = self.resident_name.get().strip()
        if not silent and not name:
            messagebox.showwarning("Missing Info", "Please enter Resident Name.")
            return
        if silent and not name: return 
            
        if not self.box_3d:
            if silent: return
            messagebox.showwarning("Incomplete", "Draw bounding boxes first.")
            return
        
        if self.is_submitted and not silent:
             self.lbl_status.config(text=f"Already saved {LANDMARKS[self.current_landmark_idx].split('. ')[1]}!")
             return
            
        cx, cy, cz = self.get_xyz()
        lm_str = LANDMARKS[self.current_landmark_idx]
        lm_idx = lm_str.split('.')[0]
        lm_name = lm_str.split('. ')[1]
        
        x1, x2, y1, y2, z1, z2 = self.box_3d
        
        # Legacy Format support: AP (x1, x2, z1, z2), Lat (y1, y2, z1, z2)
        # We save the unified Z into both to keep CSV compatibility
        ap_str = f"{x1:.1f};{x2:.1f};{z1:.1f};{z2:.1f}"
        lat_str = f"{y1:.1f};{y2:.1f};{z1:.1f};{z2:.1f}"
        
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
            
            msg = f"Saved {lm_name}!" if not silent else f"Auto-saved {lm_name}!"
            self.lbl_status.config(text=msg)
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
                
                for row in reader:
                    if len(row) < 10: continue
                    r_case, _, r_name, r_lm_idx = row[0], row[1], row[2], row[3]
                    
                    if r_case == self.case_id and r_name == name and r_lm_idx == lm_idx:
                        target_row = row
            
            if target_row:
                # Parse Boxes
                ap_parts = [float(x) for x in target_row[8].split(';')]
                lat_parts = [float(x) for x in target_row[9].split(';')]
                
                # Unify loading: Take X from AP, Y from Lat, Z from AP (or average)
                x1, x2 = ap_parts[0], ap_parts[1]
                y1, y2 = lat_parts[0], lat_parts[1]
                z1, z2 = ap_parts[2], ap_parts[3]
                
                self.box_3d = [x1, x2, y1, y2, z1, z2]
                self.display_annotation()
                
                # Also trigger visual check to align slices to this loaded center
                self.visual_check()
                
                self.lbl_status.config(text=f"Loaded existing: {target_row[4]}")
                self.is_submitted = True
                return True
                
        except Exception as e:
            print(f"Error loading annotation: {e}")
            
        return False

    def display_annotation(self):
        x1, x2, y1, y2, z1, z2 = self.box_3d
        
        # 1. AP (X-Z)
        if self.rect_ap: self.rect_ap.remove()
        self.rect_ap = Rectangle((min(x1, x2), min(z1, z2)), abs(x2-x1), abs(z2-z1),
                                 linewidth=1, edgecolor='red', facecolor='none')
        self.ax_ap.add_patch(self.rect_ap)
        
        # 2. Lat (Y-Z)
        if self.rect_lat: self.rect_lat.remove()
        self.rect_lat = Rectangle((min(y1, y2), min(z1, z2)), abs(y2-y1), abs(z2-z1),
                                  linewidth=1, edgecolor='red', facecolor='none')
        self.ax_lat.add_patch(self.rect_lat)
        
        # 3. Axial (X-Y)
        if self.rect_axial: self.rect_axial.remove()
        self.rect_axial = Rectangle((min(x1, x2), min(y1, y2)), abs(x2-x1), abs(y2-y1),
                                    linewidth=1, edgecolor='red', facecolor='none')
        self.ax_axial.add_patch(self.rect_axial)
        
        # 4. Coronal (X-Z)
        if self.rect_coronal: self.rect_coronal.remove()
        self.rect_coronal = Rectangle((min(x1, x2), min(z1, z2)), abs(x2-x1), abs(z2-z1),
                                      linewidth=1, edgecolor='red', facecolor='none')
        self.ax_coronal.add_patch(self.rect_coronal)
        
        # 5. Sagittal (Y-Z)
        if self.rect_sagittal: self.rect_sagittal.remove()
        self.rect_sagittal = Rectangle((min(y1, y2), min(z1, z2)), abs(y2-y1), abs(z2-z1),
                                       linewidth=1, edgecolor='red', facecolor='none')
        self.ax_sagittal.add_patch(self.rect_sagittal)
        
        self.canvas.draw()    
        
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()

    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    if not os.path.exists(data_dir): os.makedirs(data_dir, exist_ok=True)
    
    root = tk.Tk()
    
    # 1. Hide Root initially
    root.withdraw()
    
    # 2. Show Login Dialog
    login = LoginDialog(root)
    
    # 3. Check Result
    if not login.result_name:
        root.destroy()
        sys.exit(0)
        
    # 4. Success - Setup Main App
    root.deiconify()
    # root.state("zoomed") is handled in TkAnnotator.__init__
    
    app = TkAnnotator(root, data_dir, resident_name=login.result_name)
    
    if args.test:
        print("Setup GUI complete in test mode.")
        root.update()
        root.destroy()
    else:
        root.mainloop()
