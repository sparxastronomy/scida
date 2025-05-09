"""
Defines a series representing a Gadget-style simulation.
"""

import logging
import os
import pathlib
from pathlib import Path

from scida.discovertypes import _determine_mixins, _determine_type
from scida.interface import create_datasetclass_with_mixins
from scida.series import DatasetSeries

log = logging.getLogger(__name__)


class GadgetStyleSimulation(DatasetSeries):
    """A series representing a Gadget-style simulation."""

    def __init__(
        self,
        path,
        prefix_dict: dict | None = None,
        subpath_dict: dict | None = None,
        arg_dict: dict | None = None,
        lazy=True,
        **interface_kwargs,
    ):
        """
        Initialize a GadgetStyleSimulation object.

        Parameters
        ----------
        path: str
            Path to the simulation folder, should contain "output" folder.
        prefix_dict: dict
        subpath_dict: dict
        arg_dict: dict
        lazy: bool
        interface_kwargs: dict
        """
        self.path = path
        self.name = os.path.basename(path)
        if prefix_dict is None:
            prefix_dict = {}
        if subpath_dict is None:
            subpath_dict = {}
        if arg_dict is None:
            arg_dict = {}
        p = Path(path)
        if not (p.exists()):
            raise ValueError(f"Specified path '{path}' does not exist.")
        paths_dict = {}
        keys = []
        for d in [prefix_dict, subpath_dict, arg_dict]:
            keys.extend(list(d.keys()))
        keys = set(keys)
        for k in keys:
            subpath = subpath_dict.get(k, "output")
            sp = p / subpath
            # by default, we assume that we are given a folder that has an "output" subfolder.
            # this is not always the case - for example for subboxes.
            # in such case, we attempt to continue with the given path.
            if not sp.exists():
                sp = p

            # normally, runs have subfolders for each snapshot...
            found_prefix = False
            prefix = _get_snapshotfolder_prefix(sp)
            prefix = prefix_dict.get(k, prefix)
            if not sp.exists():
                if k != "paths":
                    continue  # do not require optional sources
                raise ValueError("Specified path '%s' does not exist." % (p / subpath))
            fns = os.listdir(sp)
            prfxs = {f.split("_")[0] for f in fns if f.startswith(prefix)}
            if len(prfxs) == 0:
                if k != "paths":
                    continue  # do not require optional sources
            else:
                found_prefix = True
                prfx = prfxs.pop()
            # ... however, sometimes runs have single-file hdf5 snapshots
            if not found_prefix:
                h5files = [f for f in fns if f.endswith(".hdf5")]
                # we only test "snap" prefix for now...
                prfx_tmp = {"gpaths": "group", "paths": "snap"}.get(k)
                if prfx_tmp is not None:
                    files = [f.split("_")[0] for f in h5files if f.startswith(prfx_tmp + "_")]
                    if len(files) > 1:
                        prfx = prfx_tmp
                        found_prefix = True

            if not found_prefix:
                raise ValueError(f"Could not find any files with prefix '{prefix}' in '{sp}'.")

            paths = sorted(sp.glob(prfx + "_*"))
            # sometimes there are backup folders with different suffix, exclude those.

            # now sort by snapshot order
            paths = [p for p in paths if str(p).split("_")[-1].isdigit() or str(p).endswith(".hdf5")]
            # attempt sorting
            try:
                nmbrs = [int(str(p).replace(".hdf5", "").split("_")[-1]) for p in paths]
                paths = [p for _, p in sorted(zip(nmbrs, paths, strict=False))]
            except:  # noqa: E722
                pass
            paths_dict[k] = paths

        # make sure we have the same amount of paths respectively
        length = None
        mismatch_length = False
        for k in paths_dict.keys():
            paths = paths_dict[k]
            if length is None:
                length = len(paths)
            else:
                if length != len(paths):
                    mismatch_length = True
        if mismatch_length:
            msg = """Mismatch between number of groups and snapshots.
                     Only loading groups that have a snapshot associated."""
            log.info(msg)
            # extract ids
            paths = paths_dict["paths"]
            ids = [int(str(p).split("_")[-1]) for p in paths]
            for k in paths_dict.keys():
                if k == "paths":
                    continue
                paths = paths_dict[k]
                paths_dict[k] = [p for p in paths if int(str(p).split("_")[-1]) in ids]

        paths = paths_dict.pop("paths", None)
        if paths is None:
            raise ValueError("Could not find any snapshot paths.")
        p = paths[0]
        cls = _determine_type(p)[1][0]

        mixins = _determine_mixins(path=p)
        cls = create_datasetclass_with_mixins(cls, mixins)

        kwargs = {arg_dict.get(k, "catalog"): paths_dict[k] for k in paths_dict.keys()}
        kwargs.update(**interface_kwargs)

        super().__init__(paths, datasetclass=cls, lazy=lazy, **kwargs)


def _get_snapshotfolder_prefix(path) -> str:
    """Try to infer the snapshot folder prefix"""
    p = pathlib.Path(path)
    if not p.exists():
        raise ValueError(f"Specified path '{path}' does not exist.")
    fns = os.listdir(p)
    fns = [f for f in fns if os.path.isdir(p / f)]
    # find most occuring prefix
    prefixes = [f.split("_")[0] for f in fns]
    if len(prefixes) == 0:
        return ""
    prefix = max(set(prefixes), key=prefixes.count)
    return prefix
