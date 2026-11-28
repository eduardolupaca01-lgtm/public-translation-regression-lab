# -*- coding: ascii -*-
# Frozen Python 2.3 launchers may execfile with different globals/locals.
import os
namespace={"__name__":"ia_renpy_classic_start"}
execfile(os.path.join(os.environ["IA_RENPY_CLASSIC_ROOT"],"IA Traductora RenPy","classic_start.py"),namespace,namespace)
namespace["launch_from_environment"]()
