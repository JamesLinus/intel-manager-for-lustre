#
# ========================================================
# Copyright (c) 2012 Whamcloud, Inc.  All rights reserved.
# ========================================================


import json
from re import escape

from django.db import models
from chroma_core.lib.job import DependOn, Step, DependAll
from polymorphic.models import DowncastMetaclass

from chroma_core.models.jobs import Job
from chroma_core.models.target import ManagedMgs, ManagedMdt, ManagedOst
from chroma_core.models.filesystem import ManagedFilesystem


class ConfParamStep(Step):
    idempotent = False

    def run(self, kwargs):
        from chroma_core.models import ConfParam
        conf_param = ConfParam.objects.get(pk = kwargs['conf_param_id']).downcast()

        self.invoke_agent(conf_param.mgs.primary_server(),
                "set-conf-param --args %s" % escape(json.dumps({
                    'key': conf_param.get_key(), 'value': conf_param.value})))


class ConfParamVersionStep(Step):
    idempotent = True

    def run(self, kwargs):
        from chroma_core.models import ManagedMgs
        ManagedMgs.objects.\
            filter(pk = kwargs['mgs_id']).\
            update(conf_param_version_applied = kwargs['version'])


class ApplyConfParams(Job):
    mgs = models.ForeignKey(ManagedMgs)

    opportunistic_retry = True

    class Meta:
        app_label = 'chroma_core'

    def description(self):
        return "Update conf_params on %s" % (self.mgs.primary_server())

    def get_steps(self):
        from chroma_core.models import ConfParam
        from chroma_core.lib.job import job_log
        new_params = ConfParam.objects.filter(version__gt = self.mgs.conf_param_version_applied, mgs = self.mgs).order_by('version')
        steps = []

        new_param_count = new_params.count()
        if new_param_count > 0:
            job_log.info("ApplyConfParams %d, applying %d new conf_params" % (self.id, new_param_count))
            # If we have some new params, create N ConfParamSteps and one ConfParamVersionStep
            highest_version = 0
            for param in new_params:
                steps.append((ConfParamStep, {"conf_param_id": param.id}))
                highest_version = max(highest_version, param.version)
            steps.append((ConfParamVersionStep, {"mgs_id": self.mgs.id, "version": highest_version}))
        else:
            # If we have no new params, no-op
            job_log.warning("ApplyConfParams %d, mgs %d has no params newer than %d" % (self.id, self.mgs.id, self.mgs.conf_param_version_applied))
            from chroma_core.lib.job import NullStep
            steps.append((NullStep, {}))

        return steps

    def get_deps(self):
        deps = [DependOn(self.mgs, 'mounted')]
        new_params = ConfParam.objects.filter(version__gt = self.mgs.conf_param_version_applied, mgs = self.mgs).order_by('version')
        targets = set()
        for param in new_params:
            param = param.downcast()
            if hasattr(param, 'mdt'):
                targets.add(param.mdt)
            if hasattr(param, 'ost'):
                targets.add(param.ost)
            if hasattr(param, 'filesystem'):
                targets.add(ManagedMdt._base_manager.get(filesystem = param.filesystem))

        for target in targets:
            deps.append(DependOn(target, 'mounted', acceptable_states = target.not_states(['unformatted', 'formatted'])))

        return DependAll(deps)


class ConfParam(models.Model):
    __metaclass__ = DowncastMetaclass
    mgs = models.ForeignKey(ManagedMgs)
    key = models.CharField(max_length = 512)
    # A None value means "lctl conf_param -d", i.e. clear the setting
    value = models.CharField(max_length = 512, blank = True, null = True)
    version = models.IntegerField()

    class Meta:
        app_label = 'chroma_core'

    @staticmethod
    def get_latest_params(queryset):
        # Assumption: conf params don't experience high flux, so it's not
        # obscenely inefficient to pull all historical values out of the DB before picking
        # the latest ones.
        from collections import defaultdict
        by_key = defaultdict(list)
        for conf_param in queryset:
            by_key[conf_param.get_key()].append(conf_param)

        result_list = []
        for key, conf_param_list in by_key.items():
            conf_param_list.sort(lambda a, b: cmp(b.version, a.version))
            result_list.append(conf_param_list[0])

        return result_list

    def get_key(self):
        """Subclasses to return the fully qualified key, e.g. a FilesystemConfParam
           prepends the filesystem name to self.key"""
        return self.key


class FilesystemClientConfParam(ConfParam):
    filesystem = models.ForeignKey(ManagedFilesystem)

    class Meta:
        app_label = 'chroma_core'

    def __init__(self, *args, **kwargs):
        super(FilesystemClientConfParam, self).__init__(*args, **kwargs)
        self.mgs = self.filesystem.mgs.downcast()

    def get_key(self):
        return "%s.%s" % (self.filesystem.name, self.key)


class FilesystemGlobalConfParam(ConfParam):
    filesystem = models.ForeignKey(ManagedFilesystem)

    def __init__(self, *args, **kwargs):
        super(FilesystemGlobalConfParam, self).__init__(*args, **kwargs)
        self.mgs = self.filesystem.mgs.downcast()

    def get_key(self):
        return "%s.%s" % (self.filesystem.name, self.key)

    class Meta:
        app_label = 'chroma_core'


class MdtConfParam(ConfParam):
    # TODO: allow setting MDT to None to allow setting the param for
    # all MDT on an MGS (and set this param for MDT in RegisterTargetJob)
    mdt = models.ForeignKey(ManagedMdt)

    def __init__(self, *args, **kwargs):
        super(MdtConfParam, self).__init__(*args, **kwargs)
        self.mgs = self.mdt.filesystem.mgs.downcast()

    def get_key(self):
        return "%s.%s" % (self.mdt.name, self.key)

    class Meta:
        app_label = 'chroma_core'


class OstConfParam(ConfParam):
    # TODO: allow setting OST to None to allow setting the param for
    # all OSTs on an MGS (and set this param for OSTs in RegisterTargetJob)
    ost = models.ForeignKey(ManagedOst)

    def __init__(self, *args, **kwargs):
        super(OstConfParam, self).__init__(*args, **kwargs)
        self.mgs = self.ost.filesystem.mgs.downcast()

    def get_key(self):
        return "%s.%s" % (self.ost.name, self.key)

    class Meta:
        app_label = 'chroma_core'
