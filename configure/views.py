
from django.shortcuts import render_to_response, redirect, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseBadRequest
from django import forms

from monitor.models import *
from configure.models import *

# IMPORTANT
# These views are implicitly transactions.  If you create an object and then 
# submit a celery job that does something to it, the job could execute before
# the transaction is committed, and fail because the object doesn't exist.
# If you create an object which you're going to refer to in a celery job,
# then commit your transaction before starting your celery job

def _create_target_mounts(node, target, failover_host = None):
    primary = ManagedTargetMount(
        block_device = node,
        target = target,
        host = node.host, 
        mount_point = target.default_mount_path(node.host),
        primary = True)
    primary.save()

    if failover_host:
        failover = ManagedTargetMount(
            block_device = None,
            target = target,
            host = failover_host, 
            mount_point = target.default_mount_path(failover_host),
            primary = False)
        failover.save()
        return [primary, failover]
    else:
        return [primary]

def _set_target_states(form, targets, mounts):
    assert(isinstance(form, CreateTargetsForm))
    from configure.lib.state_manager import StateManager
    if form.cleaned_data['start_now']:
        for mount in mounts:
            if mount.primary:
                StateManager.set_state(mount, 'mounted')
    elif form.cleaned_data['register_now']:
        for target in targets:
            StateManager.set_state(target, 'registered')
    elif form.cleaned_data['format_now']:
        for target in targets:
            StateManager.set_state(target, 'formatted')


class CreateTargetsForm(forms.Form):
    format_now = forms.BooleanField(required = False, initial = True)
    register_now = forms.BooleanField(required = False, initial = True)
    start_now = forms.BooleanField(required = False, initial = True)

    def clean(self):
        cleaned_data = self.cleaned_data
        format_now = cleaned_data.get("format_now")
        register_now = cleaned_data.get("register_now")
        start_now = cleaned_data.get("start_now")

        if register_now and not format_now:
            raise forms.ValidationError("A target must be formatted to be registered.")

        return cleaned_data

def create_mgs(request, host_id):
    host = get_object_or_404(Host, id = int(host_id))
    # TODO: some UI for forcing it to accept a node which has used_hint=True
    nodes = LunNode.objects.filter(host = host, used_hint = False) 
    other_hosts = [h for h in Host.objects.all() if h != host]

    class CreateMgsForm(CreateTargetsForm):
        device = forms.ChoiceField(choices = [(n.id, n.path) for n in nodes])
        failover_partner = forms.ChoiceField(choices = [(None, 'None')] + [(h.id, h) for h in other_hosts])

    if request.method == 'GET':
        form = CreateMgsForm()
    elif request.method == 'POST':
        form = CreateMgsForm(request.POST)
        if form.is_valid():
            node = LunNode.objects.get(id = form.cleaned_data['device'])
            if form.cleaned_data['failover_partner'] and form.cleaned_data['failover_partner'] != 'None':
                failover_host = Host.objects.get(id = form.cleaned_data['failover_partner'])
            else:
                failover_host = None

            target = ManagedMgs(name='MGS')
            target.save()
            mounts = _create_target_mounts(node, target, failover_host)
            _set_target_states(form, [target], mounts)

            return redirect('configure.views.states')

    else:
        return HttpResponseBadRequest

    return render_to_response("create_mgs.html", RequestContext(request, {
        'host': host,
        'nodes': nodes,
        'other_hosts': other_hosts,
        'form': form
        }))

def create_fs(request, mgs_id):
    mgs = get_object_or_404(ManagementTarget, id = int(mgs_id))

    class CreateFsForm(forms.Form):
        name = forms.CharField(min_length = 1, max_length = 8)

    if request.method == 'GET':
        form = CreateFsForm()
    elif request.method == 'POST':
        form = CreateFsForm(request.POST)
        if form.is_valid():
            fs = Filesystem(mgs = mgs, name = form.cleaned_data['name'])
            fs.save()
            return redirect('configure.views.states')
    else:
        return HttpResponseBadRequest

    return render_to_response("create_fs.html", RequestContext(request, {
        'mgs': mgs,
        'form': form
        }))

def create_oss(request, host_id):
    host = get_object_or_404(Host, id = int(host_id))
    # TODO: some UI for forcing it to accept a node which has used_hint=True
    nodes = host.available_lun_nodes()
    other_hosts = [h for h in Host.objects.all() if h != host]

    class CreateOssForm(CreateTargetsForm):
        filesystem = forms.ChoiceField(choices = [(f.id, f.name) for f in Filesystem.objects.all()])
        failover_partner = forms.ChoiceField(choices = [(None, 'None')] + [(h.id, h) for h in other_hosts])
        def __init__(self, *args, **kwargs):
            super(CreateTargetsForm, self).__init__(*args, **kwargs)
            self.fields.keyOrder = ['filesystem', 'failover_partner', 'format_now', 'register_now', 'start_now']
        
    class CreateOssNodeForm(forms.Form):
        def __init__(self, node, *args, **kwargs):
            self.node = node
            super(CreateOssNodeForm, self).__init__(*args, **kwargs)
        use = forms.BooleanField(required=False)

    if request.method == 'GET':
        node_forms = []
        for node in nodes:
            node_forms.append(CreateOssNodeForm(node, initial = {
                'node_id': node.id,
                'node_name': node.path,
                'use': False
                }, prefix = "%d" % node.id))

        form = CreateOssForm(prefix = 'create')
    elif request.method == 'POST':
        node_forms = []
        for node in nodes:
            node_form = CreateOssNodeForm(node, data = request.POST, prefix = "%d" % node.id)
            # These are just checkboxes
            assert(node_form.is_valid())
            node_forms.append(node_form)
        form = CreateOssForm(request.POST, prefix = 'create')
        if form.is_valid():
            if form.cleaned_data['failover_partner'] and form.cleaned_data['failover_partner'] != 'None':
                failover_host = Host.objects.get(id = form.cleaned_data['failover_partner'])
            else:
                failover_host = None
            filesystem = Filesystem.objects.get(id=form.cleaned_data['filesystem'])

            all_targets = []
            all_mounts = []
            for node_form in node_forms:
                if node_form.cleaned_data['use']:
                    node = node_form.node

                    target = ManagedOst(filesystem = filesystem)
                    target.save()
                    all_targets.append(target)
                    mounts = _create_target_mounts(node, target, failover_host)
                    all_mounts.extend(mounts)

            _set_target_states(form, all_targets, all_mounts)
            return redirect('configure.views.states')
    else:
        return HttpResponseBadRequest

    return render_to_response("create_oss.html", RequestContext(request, {
        'host': host,
        'form': form,
        'node_forms': node_forms
        }))

def create_mds(request, host_id):
    host = get_object_or_404(Host, id = int(host_id))
    # TODO: some UI for forcing it to accept a node which has used_hint=True
    nodes = host.available_lun_nodes()
    other_hosts = [h for h in Host.objects.all() if h != host]

    filesystems = Filesystem.objects.filter(metadatatarget = None)

    class CreateMdtForm(CreateTargetsForm):
        filesystem = forms.ChoiceField(choices = [(f.id, f.name) for f in filesystems])
        device = forms.ChoiceField(choices = [(n.id, n.path) for n in nodes])
        failover_partner = forms.ChoiceField(choices = [(None, 'None')] + [(h.id, h) for h in other_hosts])

    if request.method == 'GET':
        form = CreateMdtForm()
    elif request.method == 'POST':
        form = CreateMdtForm(request.POST)

        if form.is_valid():
            node = LunNode.objects.get(id = form.cleaned_data['device'])
            if form.cleaned_data['failover_partner'] and form.cleaned_data['failover_partner'] != 'None':
                failover_host = Host.objects.get(id = form.cleaned_data['failover_partner'])
            else:
                failover_host = None
            filesystem = Filesystem.objects.get(id=form.cleaned_data['filesystem'])

            target = ManagedMdt(filesystem = filesystem)
            target.save()
            mounts = _create_target_mounts(node, target, failover_host)

            _set_target_states(form, [target], mounts)

            return redirect('configure.views.states')
    else:
        return HttpResponseBadRequest

    return render_to_response("create_mds.html", RequestContext(request, {
        'host': host,
        'form': form
        }))

def jobs(request):
    jobs = Job.objects.all().order_by("-id")
    return render_to_response("jobs.html", RequestContext(request, {
        'jobs': jobs
        }))

def jobs_json(request):
    import json
    from datetime import timedelta, datetime
    from django.db.models import Q
    jobs = Job.objects.filter(~Q(state = 'complete') | Q(created_at__gte=datetime.now() - timedelta(minutes=60)))
    jobs_dicts = []
    for job in jobs:
        jobs_dicts.append({
            'id': job.id,
            'state': job.state,
            'errored': job.errored,
            'description': job.description()
        })
    jobs_json = json.dumps(jobs_dicts)

    from configure.lib.state_manager import StateManager
    state_manager = StateManager()

    from django.core.urlresolvers import reverse
    from django.contrib.contenttypes.models import ContentType
    from itertools import chain
    stateful_objects = []
    klasses = [ManagedTarget, ManagedHost, ManagedTargetMount]
    for i in chain(*[k.objects.all() for k in klasses]):
        actions = []
        transitions = state_manager.available_transitions(i)
        if transitions == None:
            busy = True
        else:
            busy = False
            for transition in transitions:
                actions.append({
                    "name": transition['state'],
                    "caption": transition['verb'],
                    "url": reverse('configure.views.set_state', kwargs={
                        "content_type_id": "%s" % i.content_type_id,
                        "stateful_object_id": "%s" % i.id,
                        "new_state": transition['state']
                        }),
                    "ajax": True
                    })
        
        can_create_mds = (MetadataTarget.objects.count() != Filesystem.objects.count())
        can_create_oss = MetadataTarget.objects.count() > 0
        if isinstance(i, ManagedMgs):
            actions.append({
                "name": "create_fs",
                "caption": "Create filesystem",
                "url": reverse('configure.views.create_fs', kwargs={"mgs_id": i.id}),
                "ajax": False
                })
        if isinstance(i, ManagedHost):
            if not i.is_mgs():
                actions.append({
                    "name": "create_mgs",
                    "caption": "Setup MGS",
                    "url": reverse('configure.views.create_mgs', kwargs={"host_id": i.id}),
                    "ajax": False
                    })
            if can_create_mds:
                actions.append({
                    "name": "create_mgs",
                    "caption": "Setup MDS",
                    "url": reverse('configure.views.create_mds', kwargs={"host_id": i.id})
                    })

            if can_create_oss:
                actions.append({
                    "name": "create_mgs",
                    "caption": "Setup OSS",
                    "url": reverse('configure.views.create_oss', kwargs={"host_id": i.id})
                    })
                
        stateful_objects.append({
            "id": i.id,
            "__str__": "%s" % i,
            "state": i.state,
            "actions": actions,
            "content_type_id": i.content_type_id,
            "busy": busy
            })

    body = json.dumps({
                'jobs': jobs_dicts,
                'stateful_objects': stateful_objects
            }, indent = 4)

    return HttpResponse(body, 'application/json')


def job(request, job_id):
    job = get_object_or_404(Job, id = job_id)
    job = job.downcast()
    
    return render_to_response("job.html", RequestContext(request, {
        'job': job
        }))

def filesystem(request, filesystem_id):
    filesystem = get_object_or_404(Filesystem, id = filesystem_id)
    
    return render_to_response("filesystem.html", RequestContext(request, {
        'filesystem': filesystem
        }))



def states(request):
    klasses = [ManagedTarget, ManagedHost, ManagedTargetMount]
    items = []
    for klass in klasses:
        items.extend(list(klass.objects.all()))

    from configure.lib.state_manager import StateManager
    state_manager = StateManager()

    from django.contrib.contenttypes.models import ContentType
    stateful_objects = []
    for i in items:
        stateful_objects.append({
            "object": i,
            "available_transitions": state_manager.available_transitions(i),
            "content_type": ContentType.objects.get_for_model(i).id
            })

    return render_to_response("states.html", RequestContext(request, {
        'stateful_objects': stateful_objects
        }))

def set_state(request, content_type_id, stateful_object_id, new_state):
    stateful_object_klass = ContentType.objects.get(id = content_type_id).model_class()
    stateful_object = stateful_object_klass.objects.get(id = stateful_object_id)

    from configure.lib.state_manager import StateManager
    transition_job = StateManager.set_state(stateful_object, new_state)

    return HttpResponse(status = 201)


