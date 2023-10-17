.. tgraphics documentation master file, created by
   sphinx-quickstart on Mon Oct 16 23:43:39 2023.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to tgraphics's documentation!
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

.. automodule:: tgraphics.component

   .. autoclass:: ComponentMeta
      :members: register, from_name, render_xml

   .. autoclass:: Pad
      :members:

   .. autoclass:: Layer
      :members:

   .. autoclass:: Row
      :members:

   .. autoclass:: Column
      :members:

   .. autoclass:: Rect
      :members:

   .. autoclass:: RoundedRect
      :members:

   .. autoclass:: Image
      :members:

   .. autoclass:: Label
      :members:

   .. autoclass:: Input
      :members:

   .. autoclass:: Window
      :members:

   .. autofunction:: use_offset_x

   .. autofunction:: use_offset_y

   .. autofunction:: use_acc_offset_x

   .. autofunction:: use_acc_offset_y

   .. autofunction:: use_scale_x

   .. autofunction:: use_scale_y

   .. autofunction:: use_acc_scale_x

   .. autofunction:: use_acc_scale_y

   .. autofunction:: use_width

   .. autofunction:: use_height

   .. autofunction:: use_hover

   .. autofunction:: use_children

   .. autofunction:: is_mounted
