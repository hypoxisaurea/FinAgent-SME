import sys, os

root = os.path.dirname(__file__)
sys.path.insert(0, root)                          # 루트 (utils 인식)
sys.path.insert(0, os.path.join(root, "backend")) # backend (agents 인식)