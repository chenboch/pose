from PyQt5.QtWidgets import *
# from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtGui import QPainter, QPen, QColor, QImage, QPixmap, QFont
from scipy.signal import find_peaks
from PyQt5.QtCore import Qt, QPointF
import numpy as np
import sys
import cv2
import os
from UI import Ui_MainWindow
import matplotlib.pyplot as plt
import pandas as pd
from argparse import ArgumentParser
from argparse import ArgumentParser
import cv2
import numpy as np
from lib.cv_thread import VideoToImagesThread
from lib.util import DataType
from lib.timer import Timer
from lib.vis_image import draw_set_line, draw_distance_infromation, draw_bbox
from lib.vis_pose import draw_points_and_skeleton, joints_dict
# from Graph.speed_graph import Speedgraph
from Widget.store import Store_Widget
from topdown_demo_with_mmdet import process_one_image
from mmengine.logging import print_log
import sys
sys.path.append("c:\\users\\chenbo\\desktop\\skeleton2d\\src\\tracker")
from pathlib import Path
from tracker.mc_bot_sort import BoTSORT
from tracker.tracking_utils.timer import Timer
from mmpose.apis import init_model as init_pose_estimator
from mmpose.utils import adapt_mmdet_pipeline
from lib.one_euro_filter import OneEuroFilter
import pyqtgraph as pg
# 設置背景和前景顏色

# from pyqtgraph import LabelItem
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

try:
    from mmdet.apis import inference_detector, init_detector
    has_mmdet = True
except (ImportError, ModuleNotFoundError):
    has_mmdet = False


class Pose_2d_Tab_Control(QMainWindow):
    def __init__(self):
        super(Pose_2d_Tab_Control, self).__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.init_var()
        self.bind_ui()

        self.add_parser()
        self.set_tracker_parser()
        self.init_model()

    def bind_ui(self):
        self.clear_table_view()
        self.ui.load_video_btn.clicked.connect(
            lambda: self.load_video(self.ui.video_label, self.db_path + "/videos/"))
        # self.ui.store_video_btn.clicked.connect(self.store_video)
        self.ui.play_btn.clicked.connect(self.play_btn_clicked)
        self.ui.back_key_btn.clicked.connect(
            lambda: self.ui.frame_slider.setValue(self.ui.frame_slider.value() - 1)
        )
        self.ui.forward_key_btn.clicked.connect(
            lambda: self.ui.frame_slider.setValue(self.ui.frame_slider.value() + 1)
        )
        self.ui.frame_slider.valueChanged.connect(self.analyze_frame)
        self.ui.ID_selector.currentTextChanged.connect(lambda: self.import_data_to_table(self.ui.frame_slider.value()))
        self.ui.correct_btn.clicked.connect(self.update_person_df)
        self.ui.show_skeleton_checkBox.setChecked(True)
        self.ui.ID_Locker.clicked.connect(self.ID_locker)
        self.ui.keypoint_table.cellActivated.connect(self.on_cell_clicked)
        self.ui.Frame_View.mousePressEvent = self.mousePressEvent
        self.ui.store_data_btn.clicked.connect(self.show_store_window)
        self.ui.li_btn.clicked.connect(self.linear_interpolation)
        self.ui.load_data_btn.clicked.connect(self.load_json)
        self.ui.smooth_data_btn.clicked.connect(self.smooth_data)
        self.ui.start_code_btn.clicked.connect(self.start_analyze_frame)
        self.ui.set_length_btn.clicked.connect(self.set_length)
        self.ui.set_fps_btn.clicked.connect(self.set_frame_ratio)

    def init_model(self):
        self.detector = init_detector(
        self.args.det_config, self.args.det_checkpoint)
        self.detector.cfg = adapt_mmdet_pipeline(self.detector.cfg)
        self.pose_estimator = init_pose_estimator(
        self.args.pose_config,
        self.args.pose_checkpoint,
        cfg_options=dict(
            model=dict(test_cfg=dict(output_heatmaps=self.args.draw_heatmap))))
        self.tracker = BoTSORT(self.tracker_args, frame_rate=30.0)
        self.smooth_tool = OneEuroFilter()
        self.timer = Timer()
        pg.setConfigOptions(foreground=QColor(113,148,116), antialias = True)

    def init_var(self):
        self.db_path = f"../../Db"
        self.is_play=False
        self.processed_images=-1
        self.fps = 30

        self.stride_num = 6
        self.speed_range = [0,14]
        self.frame_ratio = 1/120
        self.video_images=[]
        self.video_path = ""
        self.is_threading=False
        self.video_scene = QGraphicsScene()
        self.stride_scene = QGraphicsScene()
        self.speed_scene = QGraphicsScene()
        self.video_scene.clear()
        self.stride_scene.clear()
        self.speed_scene.clear()
        self.correct_kpt_idx = 0
        self.video_name = ""
        self.length_ratio = 0
        self.start_frame_num = 0
        self.line_pos = []
        self.end_line_pos = 0
        self.is_set_length = False
        self.distance_dict = {}
        self.processed_frames = set()
        self.person_df = pd.DataFrame()
        self.person_data = []
        self.label_kpt = False
        self.ID_lock = False
        self.select_id = 0
        self.select_kpt_index = 11
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.stride_graph =  pg.PlotWidget()
        self.speed_graph =  pg.PlotWidget()
        # coco
        self.kpts_dict = joints_dict()['coco']['keypoints']
        # haple
        # self.kpts_dict = joints_dict()['haple']['keypoints']
            
    def add_parser(self):
        self.parser = ArgumentParser()
        self.parser.add_argument('--det-config', default='../mmpose_main/demo/mmdetection_cfg/rtmdet_m_640-8xb32_coco-person.py', help='Config file for detection')
        self.parser.add_argument('--det-checkpoint', default='../../Db/pretrain/vit_pose_pth/rtmdet_m_8xb32-100e_coco-obj365-person-235e8209.pth', help='Checkpoint file for detection')
        self.parser.add_argument('--pose-config', default='../mmpose_main/configs/body_2d_keypoint/topdown_heatmap/coco/td-hm_ViTPose-base_8xb64-210e_coco-256x192.py', help='Config file for pose')
        self.parser.add_argument('--pose-checkpoint', default='../../Db/pretrain/vit_pose_pth/210/work_dirs/td-hm_ViTPose-base_8xb64-210e_coco-256x192/best_coco_AP_epoch_210.pth', help='Checkpoint file for pose')
        # self.parser.add_argument('--pose-config', default='../mmpose_main/configs/body_2d_keypoint/topdown_heatmap/haple/ViTPose_base_simple_halpe_256x192.py', help='Config file for pose')
        # self.parser.add_argument('--pose-checkpoint', default='../../Db/pretrain/best_coco_AP_epoch_f9_8.pth', help='Checkpoint file for pose')
        self.parser.add_argument(
        '--det-cat-id',
        type=int,
        default=0,
        help='Category id for bounding box detection model')
        self.parser.add_argument(
            '--bbox-thr',
            type=float,
            default=0.3,
            help='Bounding box score threshold')
        self.parser.add_argument(
            '--nms-thr',
            type=float,
            default=0.3,
            help='IoU threshold for bounding box NMS')
        self.parser.add_argument(
            '--kpt-thr',
            type=float,
            default=0.3,
            help='Visualizing keypoint thresholds')
        self.parser.add_argument(
            '--draw-heatmap',
            action='store_true',
            default=False,
            help='Draw heatmap predicted by the model')
        self.parser.add_argument(
            '--show-kpt-idx',
            action='store_true',
            default=False,
            help='Whether to show the index of keypoints')
        self.parser.add_argument(
            '--skeleton-style',
            default='mmpose',
            type=str,
            choices=['mmpose', 'openpose'],
            help='Skeleton style selection')
        self.parser.add_argument(
            '--radius',
            type=int,
            default=3,
            help='Keypoint radius for visualization')
        self.parser.add_argument(
            '--thickness',
            type=int,
            default=1,
            help='Link thickness for visualization')
        self.parser.add_argument(
            '--show-interval', type=int, default=0, help='Sleep seconds per frame')
        self.parser.add_argument(
            '--alpha', type=float, default=0.8, help='The transparency of bboxes')
        self.parser.add_argument(
            '--draw-bbox', action='store_true', help='Draw bboxes of instances')
        self.args = self.parser.parse_args()

    def set_tracker_parser(self):
        parser = ArgumentParser()
        # tracking args
        parser.add_argument("--track_high_thresh", type=float, default=0.3, help="tracking confidence threshold")
        parser.add_argument("--track_low_thresh", default=0.05, type=float, help="lowest detection threshold")
        parser.add_argument("--new_track_thresh", default=0.4, type=float, help="new track thresh")
        parser.add_argument("--track_buffer", type=int, default=360, help="the frames for keep lost tracks")
        parser.add_argument("--match_thresh", type=float, default=0.8, help="matching threshold for tracking")
        parser.add_argument("--aspect_ratio_thresh", type=float, default=1.6,
                            help="threshold for filtering out boxes of which aspect ratio are above the given value.")
        parser.add_argument('--min_box_area', type=float, default=10, help='filter out tiny boxes')
        parser.add_argument("--fuse-score", dest="mot20", default=True, action='store_true',
                            help="fuse score and iou for association")

        # CMC
        parser.add_argument("--cmc-method", default="sparseOptFlow", type=str, help="cmc method: sparseOptFlow | files (Vidstab GMC) | orb | ecc")

        # ReID
        parser.add_argument("--with-reid", dest="with_reid", default=False, action="store_true", help="with ReID module.")
        parser.add_argument("--fast-reid-config", dest="fast_reid_config", default=r"fast_reid/configs/MOT17/sbs_S50.yml",
                            type=str, help="reid config file path")
        parser.add_argument("--fast-reid-weights", dest="fast_reid_weights", default=r"pretrained/mot17_sbs_S50.pth",
                            type=str, help="reid config file path")
        parser.add_argument('--proximity_thresh', type=float, default=0.5,
                            help='threshold for rejecting low overlap reid matches')
        parser.add_argument('--appearance_thresh', type=float, default=0.25,
                            help='threshold for rejecting low appearance similarity reid matches')

        self.tracker_args = parser.parse_args()

        self.tracker_args.jde = False
        self.tracker_args.ablation = False

    def load_video(self, label_item, path):
        if self.is_play:
            QMessageBox.warning(self, "讀取影片失敗", "請先停止播放影片!")
            return
        self.init_var()
        
        self.video_path = self.load_data(
                label_item, path, None, DataType.VIDEO)       
        # no video found
        if self.video_path == "":
            return
        label_item.setText("讀取影片中...")
        #run image thread
        self.v_t=VideoToImagesThread(self.video_path)
        self.v_t.emit_signal.connect(self.video_to_frame)
        self.v_t.start()

    def load_data(self, label_item, dir_path="", value_filter=None, mode=DataType.DEFAULT):
        data_path = None
        if mode == DataType.FOLDER:
            data_path = QFileDialog.getExistingDirectory(
                self, mode.value['tips'], dir_path)
        else:
            name_filter = mode.value['filter'] if value_filter == None else value_filter
            data_path, _ = QFileDialog.getOpenFileName(
                None, mode.value['tips'], dir_path, name_filter)
        if label_item == None:
            return data_path
        # check exist
        if data_path:
            label_item.setText(os.path.basename(data_path))
            label_item.setToolTip(data_path)
        else:
            label_item.setText(mode.value['tips'])
            label_item.setToolTip("")
        return data_path  

    def show_image(self, image: np.ndarray, scene: QGraphicsScene, GraphicsView: QGraphicsView): 
        scene.clear()
        image = image.copy()
        image = cv2.circle(image, (0, 0), 10, (0, 0, 255), -1)
        w, h = image.shape[1], image.shape[0]
        bytesPerline = 3 * w
        qImg = QImage(image, w, h, bytesPerline, QImage.Format_RGB888).rgbSwapped()   
        pixmap = QPixmap.fromImage(qImg)
        scene.addPixmap(pixmap)
        GraphicsView.setScene(scene)
        GraphicsView.setAlignment(Qt.AlignLeft)
        GraphicsView.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)

    def show_graph(self, graph, scene, graphicview):
        graph.resize(graphicview.width(),graphicview.height())
        scene.addWidget(graph)
        graphicview.setScene(scene)
        graphicview.fitInView(scene.sceneRect(), Qt.KeepAspectRatio)

    def init_stride_graph(self):
        title = ("Stride Length (Average: 0.00m)")     
        # 創建字體對象
        font = QFont()
        font.setPixelSize(15)
        # 設置 y 軸標籤
        self.stride_graph.setLabel('left', 'Stride', font=font)
        # 設置 x 和 y 軸範圍
        self.stride_graph.setXRange(0, 3)
        self.stride_graph.setYRange(0, self.stride_num)
        # 設置 y 軸刻度
        y_ticks = [(i+1, str(i+1)) for i in np.arange(0, self.stride_num, 1)]
        self.stride_graph.getPlotItem().getAxis('left').setTicks([y_ticks])
        # 設置 x 軸刻度
        x_ticks = [(i, str(i)) for i in np.arange(0, 3.5, 0.5)]
        self.stride_graph.getPlotItem().getAxis('bottom').setTicks([x_ticks])
        # 設置 x 軸和 y 軸標籤
        self.stride_graph.setLabel('bottom', 'm', font=font)
        self.stride_graph.setWindowTitle(title)
        self.stride_graph.setTitle(title)
        self.show_graph(self.stride_graph, self.stride_scene, self.ui.stride_view)

    def init_speed_graph(self):
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        title = "Speed (Average: 0.00m/s)"
        font = QFont()
        font.setPixelSize(15)
        self.speed_graph.addLegend(offset=(150, 5), labelTextSize="10pt")
        self.speed_graph.setLabel('left', 'Velocity (m/s)')
        self.speed_graph.setLabel('bottom', f'Frame (fps: {self.ui.fps_input.value()})')
        self.speed_graph.getAxis("bottom").setStyle(tickFont=font)
        self.speed_graph.getAxis("left").setStyle(tickFont=font)
        self.speed_graph.setXRange(0, self.total_images-1)
        self.speed_graph.setYRange(self.speed_range[0], self.speed_range[1])
        self.speed_graph.setWindowTitle(title)         
        self.speed_graph.setTitle(title)
        y_ticks = [(i, str(i)) for i in np.arange(0, 16, 2)]
        self.speed_graph.getPlotItem().getAxis('left').setTicks([y_ticks])
        self.show_graph(self.speed_graph, self.speed_scene, self.ui.speed_view)

    def video_to_frame(self, video_images, fps, count):
        self.total_images = count
        self.ui.frame_slider.setMinimum(0)
        self.ui.frame_slider.setMaximum(count - 1)
        self.ui.frame_slider.setValue(0)
        self.ui.frame_num_label.setText(f'0/{count-1}')
        # show the first image of the video
        self.video_images=video_images
        self.show_image(self.video_images[0], self.video_scene, self.ui.Frame_View)
        self.init_stride_graph()
        self.init_speed_graph()
        self.ui.image_resolution_label.setText( "(0,0) -" + f" {self.video_images[0].shape[1]} x {self.video_images[0].shape[0]}")
        self.video_name = os.path.splitext(os.path.basename(self.video_path))[0]
        self.ui.video_label.setText(self.video_name)
        # height, width, _ = self.video_00      images[0].shape
        self.close_thread(self.v_t)
        self.fps = fps

    def close_thread(self, thread):
        thread.stop()
        thread = None
        self.is_threading=False
   
    def play_frame(self, start_num=0):
        for i in range(start_num, self.total_images):
            if not self.is_play:
                break
            if i > self.processed_images:
                self.processed_images = i
                # self.analyze_frame()
           
            self.ui.frame_slider.setValue(i)
            # to the last frame ,stop playing
            if i == self.total_images - 1 and self.is_play:
                self.play_btn_clicked()
            # time.sleep(0.1)
            cv2.waitKey(15)

    def merge_keypoint_datas(self, pred_instances):
        person_kpts = []
        for person in pred_instances:
            kpts = np.round(person['keypoints'][0], 2)
            kpt_scores = np.round(person['keypoint_scores'][0], 2)
            kpt_datas = np.hstack((kpts, kpt_scores.reshape(-1, 1)))
            
            # Add a boolean value to each element in kpt_datas
            kpt_datas = np.hstack((kpt_datas, np.full((len(kpt_datas), 1), False, dtype=bool)))
            person_kpts.append(kpt_datas)
        return person_kpts

    def merge_person_datas(self, frame_num, person_ids, person_bboxes, person_kpts):
        for pid, bbox, kpts in zip(person_ids, person_bboxes, person_kpts):
            new_kpts = np.zeros((len(self.kpts_dict),kpts.shape[1]))
            #haple
            # new_kpts[:26] = kpts
            # new_kpts[26:, 2] = 0.9
            #coco
            new_kpts[:17] = kpts
            new_kpts[17:, 2] = 0.9
            self.person_data.append({
                'frame_number': frame_num,
                'person_id': pid,
                'bbox': bbox,
                'keypoints': new_kpts
            })
        self.person_df = pd.DataFrame(self.person_data)

    def play_btn_clicked(self):
        if self.video_path == "":
            QMessageBox.warning(self, "無法開始播放", "請先讀取影片!")
            return
        self.is_play = not self.is_play
        if self.is_play:
            self.ui.play_btn.setText("Pause")
            self.play_frame(self.ui.frame_slider.value())
        else:
            self.ui.play_btn.setText("Play")

    def update_person_df(self):
        try:
            # 获取当前选择的人员 ID
            person_id = int(self.ui.ID_selector.currentText())
            # 获取当前帧数
            frame_num = self.ui.frame_slider.value()
            # 获取表格中的数据并更新到 DataFrame 中
            for kpt_idx in range(self.ui.keypoint_table.rowCount()):
                kpt_name = self.ui.keypoint_table.item(kpt_idx, 0).text()
                kpt_x = float(self.ui.keypoint_table.item(kpt_idx, 1).text())
                kpt_y = float(self.ui.keypoint_table.item(kpt_idx, 2).text())
                # 更新 DataFrame 中对应的值
                self.person_df.loc[(self.person_df['frame_number'] == frame_num) &
                                   (self.person_df['person_id'] == person_id), 'keypoints'].iloc[0][kpt_idx][:2] = [kpt_x, kpt_y]
            
            self.update_frame()
        except ValueError:
            print("无法将文本转换为数字")
        except IndexError:
            print("索引超出范围")

    def start_analyze_frame(self):
        for i in range(0, self.total_images-1):
            image = self.video_images[i]
            pred_instances, person_ids = process_one_image(self.args, image, self.detector, self.pose_estimator, self.tracker)
            # the keyscore > 1.0??
            person_kpts = self.merge_keypoint_datas(pred_instances)
            person_bboxes = pred_instances['bboxes']
            self.merge_person_datas(i, person_ids, person_bboxes, person_kpts)
            self.processed_frames.add(i)

    def analyze_frame(self):
        frame_num = self.ui.frame_slider.value()

        self.ui.frame_num_label.setText(
            f'{frame_num}/{self.total_images - 1}')

        # no image to analyze
        if self.total_images <= 0:
            return
        
        ori_image=self.video_images[frame_num].copy()
        image = ori_image.copy()

        if frame_num not in self.processed_frames:
            self.timer.tic()
            pred_instances, person_ids = process_one_image(self.args,image,self.detector,self.pose_estimator,self.tracker)
            average_time = self.timer.toc()
            fps= int(1/max(average_time,0.00001))
            if fps <10:
                self.ui.fps_label.setText(f"FPS: 0{fps}")
            else:
                self.ui.fps_label.setText(f"FPS: {fps}")
            # print(f"process_one_image FPS: {fps}")
            # pred_instances, person_ids = process_one_image(self.args,image,self.detector,self.pose_estimator,self.tracker)
            # the keyscore > 1.0??
            person_kpts = self.merge_keypoint_datas(pred_instances)
            person_bboxes = pred_instances['bboxes']
            self.merge_person_datas(frame_num, person_ids, person_bboxes, person_kpts)
            self.processed_frames.add(frame_num)
            
        if self.ui.frame_slider.value() == (self.total_images-1):
            self.ui.play_btn.click()

        if not self.ID_lock:
            self.import_id_to_selector(frame_num)
        else:
            self.check_id_exist(frame_num)
        self.smooth_kpt()
        self.obtain_velocity()
        self.obtain_distance()
        self.import_data_to_table(frame_num)  
        self.update_frame()
        # if len(self.stride_graph) > 0:
                 
    def update_frame(self):
        curr_person_df, frame_num= self.obtain_curr_data()
        image=self.video_images[frame_num].copy()
        
        image =  draw_set_line(image, self.line_pos)

        if len(self.distance_dict) != 0:
            image = draw_distance_infromation(image,self.distance_dict)
        # if self.ui.show_skeleton_checkBox.isChecked():
        if not curr_person_df.empty :
            #haple
            # image = draw_points_and_skeleton(image, curr_person_df, joints_dict()['haple']['skeleton_links'], 
            #                                 points_color_palette='gist_rainbow', skeleton_palette_samples='jet',
            #                                 points_palette_samples=10, confidence_threshold=0.3)
            #coco
            image = draw_points_and_skeleton(image, curr_person_df, joints_dict()['coco']['skeleton_links'], 
                                            points_color_palette='gist_rainbow', skeleton_palette_samples='jet',
                                            points_palette_samples=10, confidence_threshold=0.3)
            if self.ui.show_bbox_checkbox.isChecked():
                image = draw_bbox(curr_person_df, image)
            
        # 将原始图像直接显示在 QGraphicsView 中
        self.show_image(image, self.video_scene, self.ui.Frame_View)

    def obtain_curr_data(self):
        curr_person_df = pd.DataFrame()
        frame_num = self.ui.frame_slider.value()
        if self.ui.ID_selector.count() > 0:
            if self.ui.show_skeleton_checkBox.isChecked():
                try :
                        person_id = int(self.ui.ID_selector.currentText())
                        curr_person_df = self.person_df.loc[(self.person_df['frame_number'] == frame_num) &
                                                            (self.person_df['person_id'] == person_id)]
                except ValueError:
                    print("valueError")
            else:
                curr_person_df = self.person_df.loc[(self.person_df['frame_number'] == frame_num)]
        return curr_person_df, frame_num

    def check_id_exist(self,frame_num):
        try:
            curr_person_df = self.person_df.loc[(self.person_df['frame_number'] == frame_num)]
            if curr_person_df.empty:
                print("check_id_exist未找到特定幀的數據")
                return
            person_ids = sorted(curr_person_df['person_id'].unique())
            if self.select_id not in person_ids:
                print("True")
                self.ui.ID_Locker.click()

        except KeyError:
            # print("未找到'frame_number'或'person_id'列")
            pass

    def import_id_to_selector(self, frame_num):
        try:
            self.ui.ID_selector.clear()
            filter_person_df = self.person_df.loc[(self.person_df['frame_number'] == frame_num)]
            if filter_person_df.empty:
                # print("import_id_to_selector未找到特定幀的數據")
                self.clear_table_view()
                return

            person_ids = sorted(filter_person_df['person_id'].unique())
            for person_id in person_ids:
                if person_id == 2:
                    self.ui.ID_selector.addItem(str(person_id))

        except KeyError:
            # print("未找到'frame_number'或'person_id'列")
            pass

    def import_data_to_table(self, frame_num):
        try:
            person_id = self.ui.ID_selector.currentText()
            if person_id :
                person_id = int(person_id)
            else :
                return
            # 清空表格視圖
            self.clear_table_view()

            # 獲取特定人員在特定幀的數據
            person_data = self.person_df.loc[(self.person_df['frame_number'] == frame_num) & (self.person_df['person_id'] == person_id)]

            if person_data.empty:
                print("未找到特定人員在特定幀的數據")
                self.clear_table_view()
                return

            # 確保表格視圖大小足夠
            num_keypoints = len(self.kpts_dict)
            if self.ui.keypoint_table.rowCount() < num_keypoints:
                self.ui.keypoint_table.setRowCount(num_keypoints)

            # 將關鍵點數據匯入到表格視圖中
            for kpt_idx, kpt in enumerate(person_data['keypoints'].iloc[0]): 
                kptx, kpty, kpt_label = kpt[0], kpt[1], kpt[3]
                kpt_name = self.kpts_dict[kpt_idx]
                kpt_name_item = QTableWidgetItem(str(kpt_name))
                kptx_item = QTableWidgetItem(str(np.round(kptx,1)))
                kpty_item = QTableWidgetItem(str(np.round(kpty,1)))
                if kpt_label :
                    kpt_label_item = QTableWidgetItem("Y")
                else:
                    kpt_label_item = QTableWidgetItem("N")
                kpt_name_item.setTextAlignment(Qt.AlignRight)
                kptx_item.setTextAlignment(Qt.AlignRight)
                kpty_item.setTextAlignment(Qt.AlignRight)
                kpt_label_item.setTextAlignment(Qt.AlignRight)
                self.ui.keypoint_table.setItem(kpt_idx, 0, kpt_name_item)
                self.ui.keypoint_table.setItem(kpt_idx, 1, kptx_item)
                self.ui.keypoint_table.setItem(kpt_idx, 2, kpty_item)
                self.ui.keypoint_table.setItem(kpt_idx, 3, kpt_label_item)
        # except ValueError:
        #     print("未找到人員的ID列表")
        except AttributeError:
            print("未找到人員ID")
        except KeyError:
            print("人員ID在列表中不存在")
            
    def clear_table_view(self):
        # 清空表格視圖
        self.ui.keypoint_table.clear()
        # 設置列數
        self.ui.keypoint_table.setColumnCount(4)
        # 設置列標題
        title = ["Keypoint", "X", "Y", "有無更改"]
        self.ui.keypoint_table.setHorizontalHeaderLabels(title)
        # 將列的對齊方式設置為左對齊
        header = self.ui.keypoint_table.horizontalHeader()
        for i in range(4):
            header.setDefaultAlignment(Qt.AlignLeft)

    def on_cell_clicked(self, row, column):
        self.correct_kpt_idx = row
        self.label_kpt = True
    
    def send_to_table(self, kptx, kpty, kpt_label):
    
        kptx_item = QTableWidgetItem(str(kptx))
        kpty_item = QTableWidgetItem(str(kpty))
        if kpt_label :
            kpt_label_item = QTableWidgetItem("Y")
        else:
            kpt_label_item = QTableWidgetItem("N")
        kptx_item.setTextAlignment(Qt.AlignRight)
        kpty_item.setTextAlignment(Qt.AlignRight)
        kpt_label_item.setTextAlignment(Qt.AlignRight)
        self.ui.keypoint_table.setItem(self.correct_kpt_idx, 1, kptx_item)
        self.ui.keypoint_table.setItem(self.correct_kpt_idx, 2, kpty_item)
        self.ui.keypoint_table.setItem(self.correct_kpt_idx, 3, kpt_label_item)
        self.update_person_df()

    def set_length(self):
        self.is_set_length = True
        self.real_length = self.ui.length_input.value()/100

    def mousePressEvent(self, event):
        if self.label_kpt:
            pos = event.pos()
            scene_pos = self.ui.Frame_View.mapToScene(pos)
            kptx, kpty = scene_pos.x(), scene_pos.y()
            kpt_label = 1
            if event.button() == Qt.LeftButton:
                self.send_to_table(kptx, kpty,kpt_label)
            elif event.button() == Qt.RightButton:
                kptx, kpty = 0, 0
                self.send_to_table(kptx, kpty, 0)
            self.label_kpt = False
        
        if self.is_set_length:
            pos = event.pos()
            scene_pos = self.ui.Frame_View.mapToScene(pos)
            pos_x, pos_y = scene_pos.x(), scene_pos.y()
            pos = [pos_x, pos_y]
            self.line_pos = np.append(self.line_pos, pos)
            self.update_frame()
            if len(self.line_pos) == 4:
                self.end_line_pos = self.line_pos[0]
                print(self.end_line_pos)
                pos_f = np.array([self.line_pos[0], self.line_pos[1]])
                pos_s = np.array([self.line_pos[2], self.line_pos[3]])
                length = np.linalg.norm(pos_f - pos_s)
                self.length_ratio = self.real_length/length
                print(self.length_ratio)
                self.is_set_length = False
                QMessageBox.information(self, "設定長度", "設定長度完成!")

    def smooth_data(self):
        for curr_frame_num in self.processed_frames:
            person_id = int(self.ui.ID_selector.currentText())
            if curr_frame_num == 0:
                pre_frame_num = 0
            else:
                pre_frame_num = curr_frame_num - 1
            pre_person_data = self.person_df.loc[(self.person_df['frame_number'] == pre_frame_num) &
                                                (self.person_df['person_id'] == person_id)]
            curr_person_data = self.person_df.loc[(self.person_df['frame_number'] == curr_frame_num) &
                                                (self.person_df['person_id'] == person_id)]
            if not curr_person_data.empty:
                pre_kpts = pre_person_data.iloc[0]['keypoints']
                curr_kpts = curr_person_data.iloc[0]['keypoints']
                smoothed_kpts = []
                for pre_kpt, curr_kpt in zip(pre_kpts, curr_kpts): 
                    pre_kptx, pre_kpty = pre_kpt[0], pre_kpt[1]
                    curr_kptx , curr_kpty = curr_kpt[0], curr_kpt[1]
                    if pre_kptx != 0 and pre_kpty != 0 and curr_kptx != 0 and curr_kpty !=0:                 
                        curr_kptx = self.smooth_tool(curr_kptx, pre_kptx)
                        curr_kpty = self.smooth_tool(curr_kpty, pre_kpty)
                    else:
                        pass
                    smoothed_kpts.append([curr_kptx, curr_kpty, 0.9])  # 设置可信度为默认值
                # 更新 DataFrame 中的数据
                self.person_df.at[curr_person_data.index[0], 'keypoints'] = smoothed_kpts
            else:
                print("Previous frame data not found for smooth.")
        print("Smooth process is finished.")
    
    def smooth_kpt(self):
        if self.ui.ID_selector.count() > 0 :
            person_id = int(self.ui.ID_selector.currentText())
            person_kpt = self.person_df.loc[(self.person_df['person_id'] == person_id)]['keypoints']
            if len(person_kpt) > 0 and self.start_frame_num ==0 :
                self.start_frame_num = self.ui.frame_slider.value()
            if self.start_frame_num != 0:
                curr_frame = self.ui.frame_slider.value()
                if curr_frame == 0:
                    pre_frame_num = 0
                else:
                    pre_frame_num = curr_frame - 1

            pre_person_data = self.person_df.loc[(self.person_df['frame_number'] == pre_frame_num) &
                                                (self.person_df['person_id'] == person_id)]
            curr_person_data = self.person_df.loc[(self.person_df['frame_number'] == curr_frame) &
                                                (self.person_df['person_id'] == person_id)]
            if not curr_person_data.empty and not pre_person_data.empty:
                pre_kpts = pre_person_data.iloc[0]['keypoints']
                curr_kpts = curr_person_data.iloc[0]['keypoints']
                smoothed_kpts = []
                for pre_kpt, curr_kpt in zip(pre_kpts, curr_kpts): 
                    pre_kptx, pre_kpty = pre_kpt[0], pre_kpt[1]
                    curr_kptx , curr_kpty, curr_conf, curr_label = curr_kpt[0], curr_kpt[1], curr_kpt[2], curr_kpt[3]
                    if pre_kptx != 0 and pre_kpty != 0 and curr_kptx != 0 and curr_kpty !=0:
                 
                        curr_kptx = self.smooth_tool(curr_kptx, pre_kptx)
                        curr_kpty = self.smooth_tool(curr_kpty, pre_kpty)
                    smoothed_kpts.append([curr_kptx, curr_kpty, curr_conf, curr_label])  # 设置可信度为默认值
        #         # 更新 DataFrame 中的数据
                self.person_df.at[curr_person_data.index[0], 'keypoints'] = smoothed_kpts
  
    def ID_locker(self):
        if not self.ID_lock:
            self.ui.ID_selector.setEnabled(False)
            self.select_id = int(self.ui.ID_selector.currentText())
            self.ID_lock = True
            self.ui.ID_Locker.setText("Unlock")
        else:
            self.ui.ID_Locker.setText("Lock")
            self.select_id = 0
            self.ID_lock = False
            self.ui.ID_selector.setEnabled(True)

    def show_store_window(self):
        if self.person_df.empty:
            print("no data")
            return
        else:
            self.store_window = Store_Widget(self.video_name, self.video_images, self.person_df)
            self.store_window.show()
    
    def linear_interpolation(self):
        try:
            end = self.ui.frame_slider.value()
            start = end - 30
            
            # 获取当前帧的人员数据和上一帧的人员数据
            last_person_data = self.obtain_curr_data()[0]['keypoints'].iloc[0]
            person_id = int(self.ui.ID_selector.currentText())
            curr_person_data = self.person_df.loc[(self.person_df['frame_number'] == start) &
                                                (self.person_df['person_id'] == person_id)]
            # 确保当前帧和上一帧的数据都存在
            if not curr_person_data.empty:
                curr_person_data = curr_person_data.iloc[0]['keypoints']
                self.ui.frame_slider.setValue(start)
                # 计算每个关键点的线性插值的差值
                #haple
                # diff = np.subtract(last_person_data[26:], curr_person_data[26:])
                #coco
                diff = np.subtract(last_person_data[17:], curr_person_data[17:])
                diff[:, 2] = 0.9
                # 对后续帧应用线性插值
                i = 1
                for frame_num in range(start, end):
                    for index, row in self.person_df[self.person_df['frame_number'] == frame_num].iterrows():
                        relative_distance = i / (end - start)  # 计算相对距离
                        #haple
                        # self.person_df.at[index, 'keypoints'][26:] = np.add(curr_person_data[26:], relative_distance * diff)
                        #coco
                        self.person_df.at[index, 'keypoints'][17:] = np.add(curr_person_data[17:], relative_distance * diff)
                    i += 1
            else:
                print("Previous frame data not found for interpolation.")
        except UnboundLocalError:
            print("An error occurred in linear_interpolation function")
        except ValueError:
            print("ValueError occurred in linear_interpolation function")

    def keyPressEvent(self, event):
            if event.key() == ord('D') or event.key() == ord('d'):
                self.ui.frame_slider.setValue(self.ui.frame_slider.value() + 1)
            elif event.key() == ord('A') or event.key() == ord('a'):
                self.ui.frame_slider.setValue(self.ui.frame_slider.value() - 1)
            else:
                super().keyPressEvent(event)

    def load_json(self):
        # 打開文件對話框以選擇 JSON 文件
        json_path, _ = QFileDialog.getOpenFileName(
            self, "选择要加载的 JSON 文件", "", "JSON 文件 (*.json)")

        # 如果用戶取消選擇文件，則返回
        if not json_path:
            return

        try:
            # 从 JSON 文件中读取数据并转换为 DataFrame
            self.person_df = pd.read_json(json_path)
            process_frame_nums = sorted(self.person_df['frame_number'].unique())
            self.processed_frames = set(process_frame_nums) 
        except Exception as e:
            print(f"加载 JSON 文件时出错：{e}")

    def set_frame_ratio(self):
        self.frame_ratio = 1 / self.ui.fps_input.value()
        print(self.frame_ratio)
        font = QFont()
        font.setPixelSize(15)
        self.speed_graph.setLabel('bottom', f'Frame (fps: {self.ui.fps_input.value()})')
        self.speed_graph.getAxis("bottom").setStyle(tickFont=font)

    def obtain_velocity(self):
        time_step = 30
        if self.ui.ID_selector.count() > 0 :
            person_id = int(self.ui.ID_selector.currentText())
            person_kpt = self.person_df.loc[(self.person_df['person_id'] == person_id)]['keypoints']
            if len(person_kpt) > 0 and self.start_frame_num == 0 :
                self.start_frame_num = self.ui.frame_slider.value()
            if self.start_frame_num != 0: 
                person_kpt = person_kpt.to_numpy()
                l_x_kpt_datas = []
                l_y_kpt_datas = []
                pos_x = []
                pos_y = []
                v = []
                t = []
                l = self.ui.frame_slider.value() - self.start_frame_num
                for i in range(l):
                    if len(person_kpt) > l or len(person_kpt) == l:
                        # 18: "頸部"
                        # 5: "左肩"
                        l_x_kpt_datas.append(person_kpt[i][5][0])
                        l_y_kpt_datas.append(person_kpt[i][5][1])
                for i in range(len(l_x_kpt_datas)):
                    if i % time_step == 0 :
                        pos_x.append([l_x_kpt_datas[i]])
                        pos_y.append([l_y_kpt_datas[i]])
                # print(pos_x)
                if len(pos_x) > 1 :
                    for i in range(len(pos_x)):
                        if i > 0:
                            pos_f = np.array([pos_x[i-1], pos_y[i-1]])
                            pos_s = np.array([pos_x[i], pos_y[i]])
                            # if pos_f[0] < self.end_line_pos: 
                            length = np.linalg.norm(pos_f - pos_s)
                            temp_v = (length * self.length_ratio) / (time_step * self.frame_ratio)
                            v.append(temp_v) 
                        else:
                            v.append(0)
                for i in range(len(v)):
                    temp_t = self.start_frame_num + i * time_step
                    t.append(temp_t)
                t = t[1:]
                v = v[1:]
                # print(t)
                # print(v)
                if len(v) > 0:
                    self.update_speed_graph(t, v)
                    # print(v)

    def obtain_distance(self):
        if self.ui.ID_selector.count() > 0:
            person_id = int(self.ui.ID_selector.currentText())
            person_kpt = self.person_df.loc[(self.person_df['person_id'] == person_id)]['keypoints']
            
            if self.start_frame_num != 0: 
                person_kpt = person_kpt.to_numpy()
                l_x_ankle_datas = []
                l_y_ankle_datas = []
                r_x_ankle_datas = []
                r_y_ankle_datas = []
                t_pos = []
                d = []
                l = self.ui.frame_slider.value() - self.start_frame_num

                for i in range(l):
                    if (len(person_kpt) > l or len(person_kpt) == l):
                        # 20: "左大腳趾"
                        # 21: "右大腳趾"
                        # 15: "左腳跟"
                        # 16: "右腳跟"
                        l_x_ankle_datas.append(person_kpt[i][15][0])
                        l_y_ankle_datas.append(person_kpt[i][15][1])
                        r_x_ankle_datas.append(person_kpt[i][16][0])
                        r_y_ankle_datas.append(person_kpt[i][16][1])
                # Find peaks in the left ankle y-coordinates
                l_peaks, _ = find_peaks(np.array(l_y_ankle_datas),distance= 10 , prominence=10,width=15)
                l_peaks = l_peaks.copy()
                # Find peaks in the right ankle y-coordinates
                r_peaks, _ = find_peaks(np.array(r_y_ankle_datas),distance=10, prominence=10,width=10)
                r_peaks = r_peaks.copy()

                if len(l_peaks)>0 and len(r_peaks)>0 :
                    if l_peaks[0] < r_peaks[0]:
                        l_peaks = l_peaks[1:]
                    else:
                        r_peaks = r_peaks[1:]


                if len(l_peaks) >0 and len(r_peaks) > 0:
                    if l_peaks[0] < r_peaks[0]:
                        for i in range(len(l_peaks)):

                            t_pos.append([l_x_ankle_datas[l_peaks[i]], l_y_ankle_datas[l_peaks[i]]])
                            if i < len(r_peaks):
                                t_pos.append([r_x_ankle_datas[r_peaks[i]], r_y_ankle_datas[l_peaks[i]]])
                    else:
                        for i in range(len(r_peaks)):
                            t_pos.append([r_x_ankle_datas[r_peaks[i]], r_y_ankle_datas[r_peaks[i]]])
                            if i < len(l_peaks):
                                t_pos.append([l_x_ankle_datas[l_peaks[i]], l_y_ankle_datas[l_peaks[i]]])
                
                prev_pos = np.array([]) 
                for i in range(len(t_pos)):
                    if i > 0:
                        curr_pos = np.array(t_pos[i])
                        t_d = np.linalg.norm(prev_pos - curr_pos)
                        d.append(np.round(t_d*self.length_ratio,2))
                        prev_pos = np.array(curr_pos)
                    else:
                        prev_pos = np.array(t_pos[0])

                if len(r_peaks)>0 and len(l_peaks)>0 and len(d)>0:
                    self.update_stride_graph(d)  
                    self.distance_dict = {'right ankle x': r_x_ankle_datas,
                                    'right ankle y': r_y_ankle_datas,
                                    'left ankle x': l_x_ankle_datas,
                                    'left ankle y': l_y_ankle_datas,
                                    'l_peaks': l_peaks,
                                    'r_peaks': r_peaks,
                                    't_pos': t_pos,
                                    'd': d}
               
    def update_stride_graph(self, d):
        # 計算平均值
        self.stride_graph.clear()
        mean = np.round(np.mean(d), 2)
        title = f'Stride Length (Average: {np.round(mean,2)}m)'  
        self.stride_graph.setTitle(title)   
        # # 創建字體對象
        font = QFont()
        font.setPixelSize(15)
        y = [(i + 1) for i in range(len(d))]
        # 添加條形圖
        md = [2*x for x in d]
        barItem = pg.BarGraphItem(x=0, y=y, height=0.3, width=md, brush='r')
        # print(d)
        self.stride_graph.addItem(barItem)
        # 添加每個值方的標籤
        for i, val in enumerate(d):
            formatted_val = "{:.2f} m".format(np.round(val,2))
            label = pg.TextItem(text=formatted_val, anchor=(0.5, 0.5), color=(0, 0, 0))
            label.setPos(3, i + 1)
            self.stride_graph.addItem(label)
            
    def update_speed_graph(self, t,v):
        self.speed_graph.clear()
        mean = np.round(np.mean(v[:max(t)]), 2)
        title = f"Speed (Average: {mean}m/s)"
        font = QFont() 
        font.setPixelSize(15)
        self.speed_graph.setXRange(min(t), min(t)+200)
        self.speed_graph.setWindowTitle(title)         
        self.speed_graph.setTitle(title)
        self.speed_graph.plot(t, v, pen='r')    
        # 設置 x 軸刻度
        x_ticks = [(i, str(i)) for i in np.arange(min(t), min(t)+200, 30)]
        self.speed_graph.getPlotItem().getAxis('bottom').setTicks([x_ticks])
        for i, val in zip(t, v):
            formatted_val = str(np.round(val,2))
            text = f"{formatted_val} m/s"
            label = pg.TextItem(text = text, anchor=(0.5, 0.5), color=(0, 0, 0))
            label.setPos(i, val+1)
            self.speed_graph.addItem(label)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Pose_2d_Tab_Control()
    window.show()
    sys.exit(app.exec_())
