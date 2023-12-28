Examples
========

Profiling
--------------------

:meth:`ocp_freecad_cam.api.Job.profile` allows creating tool paths that follow face/edge contours.

.. tabs::

   .. tab:: CadQuery

        .. literalinclude :: cq_profile.py
           :language: python

   .. tab:: Build123d
        .. literalinclude :: b3d_profile.py
           :language: python

.. image:: images/cq_profile.png


2.5D Pocketing
-------------------------

:meth:`ocp_freecad_cam.api.Job.pocket` creates tool paths for pocketing / clearing holes.

.. tabs::
   .. tab:: CadQuery
        .. literalinclude :: cq_pocket.py
           :language: python
   .. tab:: Build123d (Open pocket)
        .. literalinclude :: b3d_pocket.py
            :language: python

.. image:: images/cq_pocket.png

Open pockets
~~~~~~~~~~~~

Open pockets are tricky even in the GUI of FreeCAD. A clever trick that can be employed in our case:

1) Select the desired operation faces
2) Offset them larger (for example 1/3 tool diameter)
3) Cut the offset faces with the part/compound/solid
4) Fuse the result with the original faces

The result is a face that has been offset only the open directions.

.. image:: images/b3d_open_pocket.png

Drill
-------------------------

:meth:`ocp_freecad_cam.api.Job.drill` creates tool paths for drilling holes

.. tabs::
   .. tab:: CadQuery
        .. literalinclude :: cq_drill.py
           :language: python
   .. tab:: Build123d (todo)

.. image:: images/cq_drill.png


Helix
-------------------------

:meth:`ocp_freecad_cam.api.Job.drill` creates tool paths for milling holes using helical motion

.. tabs::
   .. tab:: CadQuery
        .. literalinclude :: cq_helix.py
           :language: python
   .. tab:: Build123d (todo)

.. image:: images/cq_helix.png


Adaptive
-------------------------

:meth:`ocp_freecad_cam.api.Job.adaptive` creates clearing/profiling tool paths using adaptive algorithms.

.. tabs::
   .. tab:: CadQuery
        .. literalinclude :: cq_adaptive.py
           :language: python
   .. tab:: Build123d (todo)

.. image:: images/cq_adaptive.png
