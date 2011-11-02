#
# ==============================
# Copyright 2011 Whamcloud, Inc.
# ==============================
# REST API Conrtoller for Lustre File systems resource monitor name space
from django.core.management import setup_environ

# Hydra server imports
import settings
setup_environ(settings)

from requesthandler import (AnonymousRequestHandler,
                            extract_request_args)
from configure.models import (ManagedFilesystem,
                            ManagedMdt,
                            ManagedMgs,
                            ManagedOst,
                            ManagedHost,
                            ManagedTargetMount)
from monitor.lib.util import sizeof_fmt

class ListFileSystems(AnonymousRequestHandler):
    def run(self,request):
        filesystems = []
        mds_hostname = ''
        for filesystem in ManagedFilesystem.objects.all():
            osts = ManagedOst.objects.filter(filesystem = filesystem)
            no_of_ost = osts.count()
            no_of_oss = len(set([tm.host for tm in ManagedTargetMount.objects.filter(target__in = osts)]))
            no_of_oss = ManagedHost.objects.filter(managedtargetmount__target__in = osts).distinct().count()
            # if FS is created but MDT is no created we still want to display fs in list
            try:
               mds_hostname = ManagedMdt.objects.get(filesystem = filesystem).primary_server().pretty_name()     
            except:
                pass
            fskbytesfree  = 0
            fskbytestotal = 0
            #fsfilesfree  = 0
            #fsfilestotal = 0
            try:
                #inodedata = filesystem.metrics.fetch_last(ManagedMdt,fetch_metrics=["filesfree", "filestotal"])
                diskdata = filesystem.metrics.fetch_last(ManagedOst,fetch_metrics=["kbytesfree", "kbytestotal"])
                if diskdata:
                    fskbytesfree  = diskdata[1]['kbytesfree']
                    fskbytestotal = diskdata[1]['kbytestotal']  
                #if inodedata:
                #    fsfilesfree  = inodedata[1]['filesfree']
                #    fsfilestotal = inodedata[1]['filestotal']
            except:
                pass 

            filesystems.append({'fsid':filesystem.id,
                                'fsname': filesystem.name,
                                'status':filesystem.status_string(),
                                'noofoss':no_of_oss,
                                'noofost':no_of_ost,
                                'mgs_hostname': filesystem.mgs.primary_server().pretty_name(),
                                'mds_hostname': mds_hostname,
                                # FIXME: the API should not be formatting these, leave it to the presentation layer
                                'kbytesused': sizeof_fmt((fskbytestotal * 1024)),
                                'kbytesfree': sizeof_fmt((fskbytesfree *1024))})

        return filesystems

class GetFileSystem(AnonymousRequestHandler):
    @extract_request_args('filesystem_id')
    def run(self,request,filesystem_id):
        fs_info = []  
        filesystem =  ManagedFilesystem.objects.get(id=filesystem_id)
        osts = ManagedOst.objects.filter(filesystem = filesystem)
        no_of_ost = osts.count()
        no_of_oss = len(set([tm.host for tm in ManagedTargetMount.objects.filter(target__in = osts)]))
        no_of_oss = ManagedHost.objects.filter(managedtargetmount__target__in = osts).distinct().count()
        mds_hostname = ''
        mds_status ='' 
        # if FS is created but MDT is no created we still want to display fs in list
        try:
            mds_hostname = ManagedMdt.objects.get(filesystem = filesystem).primary_server().pretty_name()
            mds_status   = ManagedMdt.objects.get(filesystem = filesystem).primary_server().status_string()
        except:
            pass
        try:
            fskbytesfree = 0
            fskbytestotal = 0
            fsfilesfree = 0
            fsfilestotal = 0
            inodedata = filesystem.metrics.fetch_last(ManagedMdt,fetch_metrics=["filesfree", "filestotal"])
            diskdata = filesystem.metrics.fetch_last(ManagedOst,fetch_metrics=["kbytesfree", "kbytestotal"])
            if diskdata:
                fskbytesfree  = diskdata[1]['kbytesfree']
                fskbytestotal = diskdata[1]['kbytestotal']
            if inodedata:
                fsfilesfree  = inodedata[1]['filesfree']
                fsfilestotal = inodedata[1]['filestotal']
        except:
                pass

        fs_info.append( {'fsname':filesystem.name,
                         'status':filesystem.status_string(),
                         'noofoss':no_of_oss,
                         'noofost':no_of_ost,
                         'mgs_hostname':filesystem.mgs.primary_server().pretty_name(),
                         'mds_hostname':mds_hostname,
                         'mdsstatus':mds_status,
                         # FIXME: the API should not be formatting these, leave it to the presentation layer
                         'kbytesused':sizeof_fmt((fskbytestotal * 1024)),
                         'kbytesfree':sizeof_fmt((fskbytesfree *1024)),
                         'filesfree':fsfilesfree,
                         'filestotal':fsfilestotal
        })
        return fs_info  

class GetMgtDetails(AnonymousRequestHandler):
    def run(self,request):
        all_mgt = []
        for mgt in ManagedMgs.objects.all():
            lun = mgt.managedtargetmount_set.get(primary = True).block_device.lun

            active_host_name = "---"
            if mgt.active_mount:
                active_host_name = mgt.active_mount.host.pretty_name()

            all_mgt.append({
                     'fs_names':[fs.name for fs in ManagedFilesystem.objects.filter(mgs=mgt)],
                     'id':mgt.pk,
                     'human_name': mgt.human_name(),
                     'lun_name': lun.human_name(),
                     'active_host_name': active_host_name,
                     'status':mgt.status_string(),
                     'state':mgt.state,
                     'primary_server_name':mgt.primary_server().pretty_name(),
                     'failover_server_name':mgt.managedtargetmount_set.get(primary = False).host.pretty_name()
                    })
        return all_mgt

class GetFSVolumeDetails(AnonymousRequestHandler):
    @extract_request_args('filesystem')
    def run(self,request,filesystem):
        filesystem_name = filesystem
        all_fs = []
        if filesystem_name:
            dashboard_data = Dashboard(filesystem_name)
        else:
            dashboard_data = Dashboard(None)  
        for fs in dashboard_data.filesystems:
            for fstarget in fs.targets:
                for fstarget_mount in fstarget.target_mounts:
                    all_fs.append(
                                  {
                                   'fsid':fs.item.id,
                                   'fsname':fs.item.name,  
                                   'targetid':fstarget.item.id,
                                   'targetname': fstarget.item.name,
                                   'targetdevice': str(fstarget_mount.item.block_device),
                                   'targetmount':str(fstarget_mount.item.mount_point),
                                   'targetstatus':fstarget.status(),
                                   'targetstate':str(fstarget_mount.item.state),
                                   'targetstates':fstarget_mount.item.states,
                                   'targetkind': fstarget.item.role(),
                                   'hostname':fstarget_mount.item.host.pretty_name(),
                                   'failover':''
                                  }
                                 )
        return all_fs            

class GetTargets(AnonymousRequestHandler):
    @extract_request_args('filesystem', 'kinds')
    def run(self, request, filesystem, kinds):
        kind_map = {"MGT": ManagedMgs,
                    "OST": ManagedOst,
                    "MDT": ManagedMdt}

        if kinds:
            klasses = []
            for kind in kinds:
                try:
                    klasses.append(kind_map[kind])
                except KeyError:
                    raise RuntimeError("Unknown target kind '%s' (kinds are %s)" % (kind, kind_map.keys()))
        else:
            # kinds = None, means all
            klasses = kind_map.values()

        klass_to_kind = dict([(v,k) for k,v in kind_map.items()])
        result = []
        for klass in klasses:
            kind = klass_to_kind[klass]
            targets = klass.objects.all()
            for t in targets:
                result.append({
                    'id': t.id,
                    'primary_server_name': t.primary_server().pretty_name(),
                    'kind': kind,
                    # FIXME: ManagedTarget should get an explicit 'human' string function
                    # (currently __str__ services this purpose)
                    'label': "%s" % t
                    })
        return result

# FIXME: this is actually returning information about all filesystems, and all targets
# neither of which is a 'volume'.
class GetVolumes(AnonymousRequestHandler):
    @extract_request_args('filesystem_id')
    def run(self, request, filesystem_id):
        if filesystem_id:
            return self.get_volumes_per_fs(ManagedFilesystem.objects.get(id = filesystem_id))
        else:

            volumes_list = []
            for fs in ManagedFilesystem.objects.all():
                volumes_list.extend(self.get_volumes_per_fs(fs.name))
        return volumes_list
    
    def get_volumes_per_fs (self,filesystem_name):
        volume_list = []
        filesystem = ManagedFilesystem.objects.get(name = filesystem_name)
        volume_list.append(
                           {
                            'id' : filesystem.id,
                            'name': filesystem.name,
                            'targetpath': '',
                            'targetname':'', 
                            'failover':'',
                            'kind': 'FS', #filesystem.role(),
                            'status' : filesystem.status_string()
                            }
                           )
        try:
            volume_list.append(
                                {
                                 'id' : filesystem.mgs.id,
                                 'name': filesystem.mgs.name,
                                 'targetpath' : '',
                                 'targetname':'',
                                 'failover':'',     
                                 'kind': filesystem.mgs.role(),
                                 'status' : filesystem.mgs.status_string()
                                }
                )
        except ManagedMgs.DoesNotExist:
            pass
        try:
            mdt = ManagedMdt.objects.get (filesystem = filesystem)
            volume_list.append(
                                   {
                                    'id' : mdt.id,
                                    'name': mdt.name,
                                    'targetpath': '',
                                    'targetname':'',
                                    'failover':'',  
                                    'kind': mdt.role(),
                                    'status' : mdt.status_string()
                                   }
                )            
        except ManagedMdt.DoesNotExist:
            pass
        osts = ManagedOst.objects.filter(filesystem = filesystem)
        volume_list.extend([
                            {
                             'id' : ost.id,
                             'name': ost.name,
                             'targetpath': '',
                             'targetname':'',
                             'failover':'',
                             'kind': ost.role(),
                             'status' : ost.status_string()
                            }  
                            for ost in osts
                           ])
        return volume_list

#class GetClients (AnonymousRequestHandler):
#    @extract_request_args('filesystem')
#    def run(self,request,filesystem):
#        filesystem_name = filesystem
#        if filesystem_name :
#            return self.__get_clients(filesystem_name)
#        else:
#            client_list = []
#            for filesystem in ManagedFilesystem.objects.all():
#                client_list.extend(self.__get_clients(filesystem.name))
##        return client_list
#    
#    def __get_clients(self,filesystem_name):
#        fsname = ManagedFilesystem.objects.get(name = filesystem_name)
#        return [
#                { 
#                 'id' : client.id,
#                 'host' : client.host.address,
#                 'mount_point' : client.mount_point,
#                  #'status' : self.__mountable_audit_status(client)
#                }         
#                for client in Client.objects.filter(filesystem = fsname)
#        ]

class GetServers (AnonymousRequestHandler):
    @extract_request_args('filesystem_id')
    def run(self,request,filesystem_id):
        if filesystem_id:
            fs = ManagedFilesystem.objects.get(id=filesystem_id)
            return [
                    { 
                     'id' : host.id,
                     'pretty_name': host.pretty_name(),
                     'host_address' : host.address,
                     'failnode':'',
                     'kind' : host.role() ,
                     'lnet_status' : str(host.state),
                     'lnet_states': host.states, 
                     'status':host.status_string()
                    }
                    for host in fs.get_servers()
            ]
        else:
            return [
                    {
                     'id' : host.id,
                     # FIXME: this field should just be called 'address'
                     'host_address' : host.address,
                     'pretty_name': host.pretty_name(),
                     'failnode':'',
                     'kind' : host.role() ,
                     'lnet_status': host.state,
                     'lnet_states': host.states,
                     'status':host.status_string()  
                    }
                    for host in ManagedHost.objects.all()
            ]


class GetEventsByFilter(AnonymousRequestHandler):
    @extract_request_args('hostname','severity','eventtype','scrollsize','scrollid')
    def run(self,request,hostname,severity,eventtype,scrollsize,scrollid):
        #host_name=hostname
        #severity_type=severity
        event_type=eventtype
        #scroll_size=scrollsize
        #scroll_id=scrollid
        from monitor.models import Event
        filter_args = []
        filter_kwargs = {}
        if event_type :
            from django.db.models import Q
            event_type = event_type.lower
            filter_args.append(~Q(**{event_type:None}))
        event_set = Event.objects.filter(*filter_args, **filter_kwargs).order_by('-created_at')  
        return [
                {
                 'event_created_at': event.created_at,
                 'event_host': event.host.pretty_name() if event.host else '',
                 'event_severity':str(event.severity_class()),
                 'event_message': event.message(), 
                }
                for event in event_set
        ]

class GetLatestEvents(AnonymousRequestHandler):
    def run(self,request):
        from monitor.models import Event
        return [
                {
                 'event_created_at': event.created_at,
                 'event_host': event.host.pretty_name() if event.host else '',
                 'event_severity':str(event.severity_class()), # Still need to figure out wheather to pass enum or display string
                 'event_message': event.message(),
                }
                for event in Event.objects.all().order_by('-created_at')
        ]


class GetAlerts(AnonymousRequestHandler):
    @extract_request_args('active')
    def run(self,request,active):
        from monitor.models import AlertState
        return [a.to_dict() for a in AlertState.objects.filter(active = active).order_by('end')]

class GetJobs(AnonymousRequestHandler):
    def run(self,request):
        from configure.models import Job
        from datetime import timedelta, datetime
        from django.db.models import Q
        # Only retive Job logs for past 60 minutes.
        # This need to fixed to get jobs for any time delta
        # Need input from PM    
        jobs = Job.objects.filter(~Q(state = 'complete') | Q(created_at__gte=datetime.now() - timedelta(minutes=60)))

        return [j.to_dict() for j in jobs]

class GetLogs(AnonymousRequestHandler):
    @extract_request_args('month','day','lustre')
    def run(self,request,month,day,lustre):
        import datetime
        from monitor.models import Systemevents
        display_month = int(month)
        display_day = int(day) 
        if display_month == 0:
            start_date = datetime.datetime(1970, 1, 1)
        else:
            start_date = datetime.datetime(datetime.datetime.now().year,
                                           display_month, display_day)
        log_data = []
        log_data = Systemevents.objects.filter(devicereportedtime__gt =
                                               start_date).order_by('-devicereportedtime')
        if lustre:
            log_data = log_data.filter(message__startswith=" Lustre")
    
        return[
               { 
                'message': log_entry.message,
                'service': log_entry.syslogtag,
                'date': log_entry.devicereportedtime.strftime("%b %d %H:%M:%S"),
                'host': log_entry.fromhost,
               }
               for log_entry in log_data
        ]


def gettimeslice(sample_size=10,interval=5):
    from datetime import timedelta,datetime
    current_time = datetime.now()
    data_slice = []
    for i in xrange(sample_size):
        current_time  = current_time - timedelta(seconds=interval)
        strtime  = current_time.isoformat().split('T')[1]
        data_slice.append(strtime.split('.')[0])
    return data_slice

class Dashboard:
    class StatusItem:
        def __init__(self, dashboard, item):
            self.dashboard = dashboard
            self.item = item

        def status(self):
            return self.dashboard.all_statuses[self.item]
    
    def __init__(self,filesystem_name):
        self.all_statuses = {}
        # 1 query for getting all targetmoun
        for mount in ManagedTargetMount.objects.filter(primary=True):
            # 1 query per targetmount to get any alerts
            self.all_statuses[mount] = mount.status_string()
        from collections import defaultdict
        target_mounts_by_target = defaultdict(list)
        target_mounts_by_host = defaultdict(list)
        target_params_by_target = defaultdict(list)

        for target_klass in ManagedMgs, ManagedMdt, ManagedOst:
            # 1 query to get all targets of a type
            for target in target_klass.objects.all():
                # 1 query per target to get the targetmounts
                #target_mounts = target.managedtargetmount_set.all()
                target_mounts = target.managedtargetmount_set.filter(primary=True)
                try:
                    target_mountable_statuses = dict(
                            [(m, self.all_statuses[m]) for m in target_mounts])
                except KeyError:
                    continue
                target_mounts_by_target[target].extend(target_mounts)
                for tm in target_mounts:
                    target_mounts_by_host[tm.host_id].append(tm)
                self.all_statuses[target] = target.status_string(target_mountable_statuses)

                target_params_by_target[target] = target.get_params()
        self.filesystems = []
        # 1 query to get all filesystems
        managedfilesystems = []
        if filesystem_name:
            managedfilesystems.append(ManagedFilesystem.objects.get(name=filesystem_name))
        else:
            managedfilesystems =  ManagedFilesystem.objects.all().order_by('name')

        for filesystem in managedfilesystems:
            # 3 queries to get targets (of each type)
            targets = filesystem.get_targets()
            try:
                fs_target_statuses = dict(
                        [(t, self.all_statuses[t]) for t in targets])
            except KeyError:
                continue
            self.all_statuses[filesystem] = filesystem.status_string(fs_target_statuses)
            fs_status_item = Dashboard.StatusItem(self, filesystem)
            fs_status_item.targets = []
            for target in targets:
                target_status_item = Dashboard.StatusItem(self, target)
                target_status_item.target_mounts = []
                for tm in target_mounts_by_target[target]:
                    target_mount_status_item = Dashboard.StatusItem(self, tm)
                    target_mount_status_item.target_params = target_params_by_target[target]
                    target_status_item.target_mounts.append(target_mount_status_item)
                fs_status_item.targets.append(target_status_item)

            self.filesystems.append(fs_status_item)

        self.hosts = []
        # 1 query to get all hosts
        for host in ManagedHost.objects.all().order_by('address'):
            host_tms = target_mounts_by_host[host.id]
            # 1 query to get alerts
            host_tm_statuses = dict([(tm, self.all_statuses[tm]) for tm in host_tms])
            self.all_statuses[host] = host.status_string(host_tm_statuses)
            host_status_item = Dashboard.StatusItem(self, host)
            host_status_item.target_mounts = [Dashboard.StatusItem(self, tm) for tm in host_tms]
