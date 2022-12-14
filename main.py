"""
Main file for inference and control
"""

import math
import threading
import time

import numpy as np
import cv2
import pygame as pg
import torch

from networks import VSNet
from hardware import VidCap, Board, Display


window = pg.display.set_mode((505, 600))
pg.init()
car = pg.Surface((0.9/0.25*5, 1.5/0.25*5))
car.fill((0, 0, 0))

# Read from videos
cap = VidCap(5, 640, 480)

board = Board("COM3")
display = Display(window)

time.sleep(1)
sensor_thread = threading.Thread(target=board.update_angle)
sensor_thread.start()
turn_thread = threading.Thread(target=board.turn)
turn_thread.start()

device = torch.device("cpu")
model = VSNet().to(device)
model.load_state_dict(torch.load("models/vs.pth", map_location=device))
model.eval()

edge_supress = np.vectorize(lambda x: 0.0 if x < 0.2 else x)
px = pg.Surface((5, 5))
px.set_colorkey((255, 255, 255))

kp = 0.4
bias = -3
while True:
    # Get new image
    cap.read()
    cap.imshow()

    # Inference
    img0 = torch.from_numpy(cap.img0[None, :].astype("float32"))
    img1 = torch.from_numpy(cap.img1[None, :].astype("float32"))
    img2 = torch.from_numpy(cap.img2[None, :].astype("float32"))
    img3 = torch.from_numpy(cap.img3[None, :].astype("float32"))
    img4 = torch.from_numpy(cap.img4[None, :].astype("float32"))
    img0 = torch.swapaxes(img0, 1, 3)
    img1 = torch.swapaxes(img1, 1, 3)
    img2 = torch.swapaxes(img2, 1, 3)
    img3 = torch.swapaxes(img3, 1, 3)
    img4 = torch.swapaxes(img4, 1, 3)
    img0 = torch.swapaxes(img0, 2, 3)
    img1 = torch.swapaxes(img1, 2, 3)
    img2 = torch.swapaxes(img2, 2, 3)
    img3 = torch.swapaxes(img3, 2, 3)
    img4 = torch.swapaxes(img4, 2, 3)
    img0 = img0.to(device)
    img1 = img1.to(device)
    img2 = img2.to(device)
    img3 = img3.to(device)
    img4 = img4.to(device)

    yh = model(img0, img1, img2, img3, img4)
    drivable = yh[:, :12120].reshape(120, 101)
    edge = yh[:, 12120:].reshape(120, 101)
    drivable_display = torch.minimum(torch.Tensor([255]), torch.maximum(torch.Tensor([0]), 210 + 45 * drivable))
    edge_display = torch.minimum(torch.Tensor([255]), torch.maximum(torch.Tensor([0]), 255 - 255*torch.from_numpy(edge_supress(edge.detach().numpy()))))
    # Display
    window.fill((210, 210, 210))
    for n_y, (drivable_row, edge_row) in enumerate(zip(drivable_display, edge_display)):
        for n_x, (d, e) in enumerate(zip(drivable_row, edge_row)):
            pg.draw.rect(px, (d, d, d), (0, 0, 5, 5))
            window.blit(px, (5 * n_x, 595 - (5 * n_y)))
            pg.draw.rect(px, (255, e, e), (0, 0, 5, 5))
            window.blit(px, (5 * n_x, 595 - (5 * n_y)))

    # Distance to road edge for each angle
    dist_dict = {}
    for angle in range(-30, 31, 1):
        dist_dict[f"{angle}"] = float("inf")
        for dist in range(20):
            dist = dist/4 + 0.25
            x = -dist*math.sin(angle * math.pi / 180)
            y = dist*math.cos(angle * math.pi / 180)
            i_x = round(50 + float(x) / 0.25)  # Grid size of 0.25m
            i_y = round(float(y) / 0.25 + 40)
            if edge[i_y, i_x] > 0.2 or drivable[i_y, i_x] < 0.2:
                dist_dict[f"{angle}"] = dist
                break

    angles = []
    for i, dist in enumerate((dist_dict.values())):
        if dist == max(dist_dict.values()):
            angles.append(-30 + i)
    angle = np.mean(angles)
    line = pg.Surface((505, 600))
    line.fill((255, 255, 255))
    line.set_colorkey((255, 255, 255))
    pg.draw.line(line, (30, 144, 255), (252.5, 400), (252.5 - 5*4*5*math.sin(angle*math.pi/180),
                                                   400 - 5*4*5*math.cos(angle*math.pi/180)), width=6)
    window.blit(line, (0, 0))
    window.blit(car, car.get_rect(center=(252.5, 400 + (1.5/2 - 0.2)/0.25*5)))

    steer_angle = max(min(kp*angle + bias, 20), -20)  # Scale and clip angle

    # Turn
    board.turn_deg = steer_angle

    # Update angle displays
    display.update(board, steer_angle)

    if cv2.waitKey(1) == ord("f"):
        cv2.destroyAllWindows()
        cv2.VideoCapture(0).release()
        break
