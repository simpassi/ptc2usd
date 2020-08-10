from pxr import Usd, UsdGeom, Gf
import tempfile
import json
import sys
import os
import subprocess

def lib_var():
    if sys.platform == "darwin":
        return "DYLD_LIBRARY_PATH"
    else:
        return "LD_LIBRARY_PATH"

def pixar_folder():
    if sys.platform == "darwin":
        return "/Applications/Pixar"
    else:
        return "/opt/pixar"

def find_rps():
    lib_path = os.environ.get(lib_var(), "")
    if "RenderManProServer" in lib_path:
        paths = [p for p in lib_path.split(":") if "RenderManProServer" in p]
        # first one will be respected anyways
        ver = paths[0].split("-")[-1]
        return ver, paths[0]

    folder = pixar_folder()
    if not os.path.exists(folder):
        return None, None

    vers = []
    for fld in os.listdir(folder):
        if "RenderManProServer" in fld:
            vers.append(fld)
    latest = list(sorted(vers))[-1]
    ver = latest.split("-")[-1]
    return ver, os.path.join(folder, latest)


def _dedupe_json(data):
    ret = {}
    # only lists? skip
    all_lists = True
    for a in data:
        if not isinstance(a, list):
            all_lists = False
    if all_lists:
        ret = []
        for a in data:
            ret.append(_dedupe_json(a))
        return ret

    for i, a in enumerate(data):
        if i % 2 == 0:
            k = a
        if i % 2 == 1:
            if isinstance(a, list) and k not in ["tuples", "arrays"]:
                ret[k] = _dedupe_json(a)
            else:
                ret[k] = a
    return ret


class PointCloudParser(object):
    def __init__(self, path):
        self.path = path
        self._data = {}

    def parse(self):
        return

    def populate_point_object(self, pts_obj):
        return

    def write_usd(self, path):
        use_stdout = False
        if path == "-":
            use_stdout = True
            std_f, path = tempfile.mkstemp("{}.usda".format(os.path.basename(self.path).split(".")[0]))
        stage = Usd.Stage.CreateNew(path)
        xform = UsdGeom.Xform.Define(stage, '/points')
        pts_obj = UsdGeom.Points.Define(stage, '/points/pts')
        self.populate_point_object(pts_obj)
        stage.GetRootLayer().Save()
        if use_stdout:
            with open(path, "r") as f:
                for line in f:
                    sys.stdout.write(line)


class JSONPointParser(PointCloudParser):
    def __init__(self, path):
        PointCloudParser.__init__(self, path)

    def parse(self):
        with open(self.path) as f:
            tmp_data = json.load(f)
            # handle data tuples
            self._data = _dedupe_json(tmp_data)
        if "attributes" in self._data:
            self.attributes = self._data["attributes"]

    def populate_point_object(self, pts_obj):
        for p_attr in self.attributes.get("pointattributes", []):
            if p_attr[0]["name"] == "P":
                values = p_attr[1]["values"]["tuples"]
                #pts = UsdGeom.Points(xform)
                attr = pts_obj.CreatePointsAttr()
                all_points = []
                wths = []
                for p in values:
                    all_points.append(Gf.Vec3f(p[0],p[1],p[2]))
                    wths.append(1.0)
                attr.Set(all_points)
                w_attr = pts_obj.CreateWidthsAttr(wths)
            elif p_attr[0]["name"] == "v":
                values = p_attr[1]["values"]["tuples"]
                #pts = UsdGeom.Points(xform)
                all_vels = []
                wths = []
                for p in values:
                    all_vels.append(Gf.Vec3f(p[0],p[1],p[2]))
                pts_obj.CreateVelocitiesAttr(all_vels)


class PTCParser(PointCloudParser):
    def __init__(self, path):
        PointCloudParser.__init__(self, path)

    def parse(self):
        rel_exec = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "{}_pt".format(sys.platform))
        if not os.path.exists(rel_exec):
            print("No binary available for platform {}".format(sys.platform))
            return
        ver, rps = find_rps()
        if ver is None:
            print("Couldn't find a RenderManProServer folder in default locations")
            print(" or in the {} variable!".format(lib_var()))
            return
        lib_folder = os.path.join(rps, "lib")
        if not lib_folder in os.environ.get(lib_var(), ""):
            os.environ[lib_var()] = "{}:{}".format(lib_folder, os.environ.get(lib_var(), ""))

        pt_p = subprocess.Popen([rel_exec, self.path], stdout=subprocess.PIPE)
        self._data["points"] = []
        for line in pt_p.stdout:
            self._data["points"].append([float(x) for x in line.strip("\n").split(",")])

    def populate_point_object(self, pts_obj):
        attr = pts_obj.CreatePointsAttr()
        all_points = []
        wths = []
        for p in self._data["points"]:
            all_points.append(Gf.Vec3f(p[0],p[1],p[2]))
            wths.append(p[6])
        attr.Set(all_points)
        w_attr = pts_obj.CreateWidthsAttr(wths)


if len(sys.argv)<3:
    print("USAGE:\n\tptc2usd <in_file.(ptc|json)> <out_file.usd[a]>")
    sys.exit(0)

if sys.argv[1].lower().endswith(".json"):
    pp = JsonPointParser(sys.argv[1])
    pp.parse()
    pp.write_usd(sys.argv[2])
else:
    pp = PTCParser(sys.argv[1])
    pp.parse()
    pp.write_usd(sys.argv[2])