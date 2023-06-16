import cadquery as cq

from ocp_freecad_cam.api import Endmill, Job

wp = cq.Workplane().box(5, 5, 2)

top = wp.faces(">Z").workplane()
profile_shape = wp.faces("<Z")

tool = Endmill(diameter="1 mm")
job = Job(top, wp)
job = job.profile(profile_shape, tool)
