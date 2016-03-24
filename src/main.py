import libvirt
from flask import Flask, jsonify, make_response, request
import xml, attach
from flask import request
from flask import render_template
from xml import create_xml
import json
from pprint import pprint
import uuid
import MySQLdb
import subprocess
import re
import linecache
import sys
import rados
import rbd
import os
from random import choice

VOL_Names = []
POOL = 'test'

app = Flask(__name__)
CONF_FILE = "/etc/ceph/ceph.conf"
db = MySQLdb.connect(host="localhost", # your host, usually localhost
                     user="root", # your username
                      passwd="mysql", # your password
                      )

# FUCK
def sql():
    cur = db.cursor() 
    sql = 'CREATE DATABASE IF NOT EXISTS VM_INFO';
    cur.execute(sql)

    sql = 'USE VM_INFO';
    cur.execute(sql)
    
    sql = 'CREATE TABLE  IF NOT EXISTS vm( id INT(10) AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), uuid VARCHAR(255),  hostID INT, typeID INT)'
    cur.execute(sql)
    
    sql = 'CREATE TABLE  IF NOT EXISTS volume( id INT(10) AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255), size INT(10), status VARCHAR(255), vmid INT(10), dev_name VARCHAR(255))'
    cur.execute(sql)
    
    return cur

cursor = sql()

#COPIED 
def establish_connection():
    cluster = rados.Rados(conffile=CONF_FILE)
    cluster.connect()
    if POOL not in cluster.list_pools():
        cluster.create_pool(POOL)
    global ioctx
    ioctx = cluster.open_ioctx(POOL)
    global rbdInstance
    rbdInstance = rbd.RBD()

@app.route("/volume/create",methods=['GET'])
def createVolume():
    arguments = request.args
    name = str(arguments['name'])
    size = int(arguments['size'])
    global VOL_Names
    if name in VOL_Names:
        return jsonify(volumeid=0)
    size = (1024**3) * size
    global rbdInstance
    global ioctx
    #try:
    rbdInstance.create(ioctx, name, size)
    os.system('sudo rbd map %s --pool %s --name client.admin'%(name,POOL))
    #except ValueError:
    volDetails = {}
    volumeID = 1234
    volDetails[str(volumeID)] = {}
    volDetails[str(volumeID)]['name'] = name
    volDetails[str(volumeID)]['size'] = size
    volDetails[str(volumeID)]['status'] = "available"
    volDetails[str(volumeID)]['VMid'] = 0
    #volDetails[str(volumeID)]['dev_name'] = getDeviceName()
    #db.vols.insert({'idto' : volumeID, 'vol' : volDetails[str(volumeID)]})

    print volDetails
    sql ="INSERT INTO {} (name, size, status, vmid, dev_name) VALUES ('{}', '{}','{}','{}', '{}')".format('volume', name, size, 'available', 0, getDeviceName())
    cursor.execute(sql)
    db.commit()
    
    sql = "SELECT * FROM volume ORDER BY id DESC LIMIT 1"
    row = cursor.execute(sql)
    for i in cursor:
        volid=i[0]
    return jsonify(volumeid=volid)


@app.route("/volume/query",methods=['GET'])
def queryVolume():
    volumeid = request.args.get('volumeid')
    sql= "SELECT * from volume WHERE id = {}".format(volumeid)
    isThere = cursor.execute(sql)
    if(isThere) :
        print cursor
        vol_query = {}
        vol_query['volumeid'] = volumeid
        for i in cursor:
            vol_query['name']= i[1]
            vol_query['size'] = i[2]
            vol_query['status'] = i[3]
            if(i[4]):
                vol_query['vmid'] = i[4]

    else :
        return "error : volumeid : "+ volumeid + " does not exist "
    return jsonify(vol_query)

@app.route("/volume/destroy",methods=['GET'])
def destroyVolume():
    arguments = request.args
    volumeid = int(arguments['volumeid'])

    sql= " SELECT * from volume WHERE id = {}".format(volumeid)    
    row = cursor.execute(sql)
    for i in cursor:
        j=i

    if(int(row)):
        try:
            imageName = str(j[1])
            print "imgname"+imageName
            os.system('sudo rbd unmap /dev/rbd/%s/%s'%(POOL,imageName))
            rbdInstance.remove(ioctx,imageName)
            sql = "DELETE FROM volume WHERE id = {}".format(volumeid)
            cursor.execute(sql)
            db.commit()
            print sql
            return jsonify(status=1)
        except ValueError:
            return jsonify(status=0)
    return jsonify(status=0)

@app.route("/volume/attach", methods=['GET'])
def attachVolume():
    arguments = request.args
    vmid = int(arguments['vmid'])
    volid = int(arguments['volumeid'])
    sql= " SELECT * from vm WHERE id = {}".format(vmid)    
    vmrow = cursor.execute(sql)
    if(int(vmrow)==0):
        return jsonify(status=0)
    for i in cursor:
        selected_machine_user = i[3]
        VM_uuid = i[2]
    
    sql= " SELECT * from volume WHERE id = {}".format(volid)    
    volrow = cursor.execute(sql)
    if(int(volrow)==0):
        return jsonify(status=0)
    for i in cursor:
        image_name=i[1]
        dev_name=i[5]
    
    ip = open(sys.argv[1]).readlines()[0].split('\n')
    ip = ip[0]
    connection = libvirt.open("qemu+ssh://" + ip + "/system")
    dom = connection.lookupByUUIDString(VM_uuid)
    confXML = attach.getXML(str(image_name), str('yash-Inspiron-3542'), str(POOL), str(dev_name))
    print str(confXML)
    try:
        dom.attachDevice(confXML)
        connection.close()

        sql="UPDATE volume SET status='attached' WHERE id={}".format(volid)   
        volrow = cursor.execute(sql)
        db.commit()

     
        sql="UPDATE volume SET vmid={} WHERE id={}".format(vmid,volid)   
        volrow = cursor.execute(sql)
        db.commit()

        return jsonify(status=1)
    except ValueError:
        print ValueError
        connection.close()
        return jsonify(status=0)

@app.route("/volume/detach", methods=['GET'])
def detachVolume():
    arguments = request.args
    volid = int(arguments['volumeid'])
    volinfo = {}
    
    sql= " SELECT * from volume WHERE id = {}".format(volid)    
    volrow = cursor.execute(sql)

    for i in cursor:
        VM_id=i[4]
        dev=i[5]
        Image_name = i[1]
    print "vmid "+str(VM_id)
    sql= " SELECT * from vm WHERE id = {}".format(VM_id)    
    volrow = cursor.execute(sql)
    for i in cursor:
        VM_name = i[1]

    ip = open(sys.argv[1]).readlines()[0].split('\n')
    ip = ip[0]
    connection = libvirt.open("qemu+ssh://" + ip + "/system")
    
    dom = connection.lookupByName(VM_name)
    confXML = attach.getXML(str(Image_name), str('yash-Inspiron-3542'), str(POOL), str(dev))
    
    try:
        dom.detachDevice(confXML)
        connection.close()

        sql="UPDATE volume SET status='available' WHERE id={}".format(volid)   
        volrow = cursor.execute(sql)
        db.commit()

     
        sql="UPDATE volume SET vmid={} WHERE id={}".format('0',volid)   
        volrow = cursor.execute(sql)
        db.commit()

        return jsonify(status=1)
    except:
        connection.close()
        return jsonify(status=0)


@app.route('/')
def hello_world():
    return 'Welcome'

def getDeviceName():
    alpha = choice('efghijklmnopqrstuvwxyz')
    numeric = choice([x for x in range(1,10)])
    return 'sd' + str(alpha) + str(numeric)

def parse_create_args():
    name = request.args.get('name')
    instance_type = int(request.args.get('instance_type'))
    image_id = request.args.get('image_id')
    with open(sys.argv[3]) as data_file:    
        data = json.load(data_file)
    return data['types'][instance_type-1]

def scheduler(mem):
    
    num_lines = sum(1 for line in open(sys.argv[1]))
    list_pm = []
    for i in range(num_lines):
        list_pm.append(open(sys.argv[1]).readlines()[i-1].split('\n')[0])
    
    print list_pm
    for i in list_pm:
        print i
        mem_free = subprocess.Popen(["ssh",i,"grep","MemFree","/proc/meminfo"],stdout=subprocess.PIPE).communicate()[0].strip('\n')
        mem_free = int(re.search('\d+',mem_free).group(0))

        if(mem < mem_free):
            return i
        else:
            continue

    return "0"


@app.route('/vm/create')
def vm_create():

    print "Starting Vm creation ... "

    name = request.args.get('name')
    instance_type = int(request.args.get('instance_type'))
    image_id = request.args.get('image_id')
    with open(sys.argv[3]) as data_file:    
        data = json.load(data_file)
    
    data = parse_create_args()
    ip = scheduler(data['ram'])
    virConnect_obj = libvirt.open("qemu+ssh://"+ip+"/system")
    vm_uuid = uuid.uuid4()
    img_path = linecache.getline(sys.argv[2], int(image_id))
    img_path = img_path[:-1]
    xml_string = create_xml(len(virConnect_obj.listDomainsID()), vm_uuid, name, data['ram'], data['cpu'], img_path)
    #print 'img_path %s'%img_path
    file_info = subprocess.Popen(["ssh",ip,"ls","/home/yash/"+img_path.split('/')[-1]], stdout=subprocess.PIPE)
    ssh_info = subprocess.Popen(["wc", "-l"], stdin=file_info.stdout, stdout=subprocess.PIPE)
    file_info.stdout.close()
    if (int(ssh_info.communicate()[0].strip('\n'))!=1):
        print "Copying the Image File to the target location ..."
        scp_status = subprocess.Popen(["scp","-3",img_path,ip+":/home/yash/"],stdout=subprocess.PIPE).communicate()[0].strip('\n')
    else:
        print "Image file already exists in the physical machine"
    
    virDomain_obj = virConnect_obj.defineXML(xml_string)
    status = virDomain_obj.create()
    domIDs = virConnect_obj.listDomainsID()
    domID  = domIDs[-1]
    print 'domID %d ' % virDomain_obj.ID()
    sql ="INSERT INTO {} (uuid, name, hostID, typeID) VALUES ('{}', '{}',1,{})".format('vm',vm_uuid, name, int(instance_type))
    print sql
    cursor.execute(sql)
    db.commit()
    
    print "STATUS"
    print status
    sql = "SELECT id FROM vm ORDER BY id DESC LIMIT 1"
    cursor.execute(sql)
    for i in cursor:
        lastRow = i
    if(status == 0):
        return "{ vmid : " + str(lastRow[0]) + "}"
    else:
        return 0

    #return render_template('display.html', Name=ID, Namex=Name, State=State, MaxMem=MaxMem, CPU=CPU, cpuTime=cpuTime)

@app.route('/vm/destroy')
def vm_destroy():
    vmid = request.args.get('vmid')
    ip = open(sys.argv[1]).readlines()[0].split('\n')
    ip = ip[0]
    virConnect_obj = libvirt.open("qemu+ssh://" + ip + "/system")
    
    sql= " SELECT * from vm WHERE id = {}".format(vmid)
    
    row = cursor.execute(sql)
    if(int(row)):
        for i in cursor:
            uuidToDestroy = i[2]
        vm = virConnect_obj.lookupByUUIDString(str(uuidToDestroy))
        if vm.info()[0] == 5 :
            virConnect_obj.lookupByUUIDString(str(uuidToDestroy)).undefine()
        else:
            virConnect_obj.lookupByUUIDString(str(uuidToDestroy)).destroy()
            virConnect_obj.lookupByUUIDString(str(uuidToDestroy)).undefine()
        
        sql = "DELETE FROM vm WHERE id = {}".format(vmid)
        cursor.execute(sql)
        db.commit()
        destroy = {}
        destroy['status'] = 1
        return json.dumps(destroy)
    else :
        destroy = {}
        destroy['status'] = 0
        return json.dumps(destroy)


@app.route('/pm/list')
def pm_list():

    num_lines = sum(1 for line in open(sys.argv[1]))
    list_pm = {}
    list_pm['pmids'] = []
    for i in range(num_lines):
            list_pm['pmids'].append(i + 1)
    return json.dumps(list_pm) 


@app.route('/pm/query')
def pm_query():
    pmid = request.args.get('pmid')
    print sys.argv[1]
    ip = open(sys.argv[1]).readlines()[int(pmid)-1].split('\n')
    ip = ip[0]
    mem_free = subprocess.Popen(["ssh",ip,"grep","MemFree","/proc/meminfo"],stdout=subprocess.PIPE).communicate()[0].strip('\n')
    mem_capacity = subprocess.Popen(["ssh",ip,"grep","MemTotal","/proc/meminfo"],stdout=subprocess.PIPE).communicate()[0].strip('\n')
    cpu_capacity = subprocess.Popen(["ssh", ip,"grep","processor","/proc/cpuinfo"], stdout=subprocess.PIPE).communicate()[0].strip('\n')
    pm_query = {}
    pm_query['pmid'] = pmid
    pm_query['capacity'] = {}
    pm_query['capacity']['cpu'] = int(cpu_capacity[-1]) + 1
    pm_query['capacity']['ram'] = mem_capacity[11:]
    pm_query['capacity']['disk'] = 'None'

    pm_query['free'] = {}
    pm_query['free']['cpu'] = "Null"
    pm_query['free']['ram'] = mem_free[10:]
    pm_query['free']['disk'] = 'None'

    pm_query['vms'] = 0
    virConnect_obj = libvirt.open("qemu+ssh://"+ip+"/system")
    vms = len(virConnect_obj.listAllDomains())
    pm_query['vms'] = vms
   
    return json.dumps(pm_query)

@app.route('/vm/query')
def vm_query():
    #Fetches the corresponding row from database and jsonifies it
    vmid = request.args.get('vmid')
    sql= " SELECT * from vm WHERE id = {}".format(vmid)
    isThere = cursor.execute(sql)
    if(isThere) :
        vm_query = {}
        vm_query['vmid'] = vmid
        for i in cursor:
            vm_query['name']= i[1]
            vm_query['instance_type'] = i[4]
            vm_query['pmid'] = i[3]
    else :
        return "0"
    return json.dumps(vm_query)

@app.route('/vm/types')
def vm_types():
    with open(sys.argv[3]) as data_file:    
        data = json.load(data_file)
    return json.dumps(data)

@app.route('/pm/listvms')
def listvms():
    pmid = request.args.get('pmid')
    sql= " SELECT * from vm WHERE hostID = {}".format(pmid)
    rows = cursor.execute(sql)
    if(rows > 0):
        listvms = {}
        listvms['vmids'] = []
        for i in cursor:
            listvms['vmids'].append(i[0])
        return json.dumps(listvms)
    else:
        return '0'

@app.route('/image/list')
def image_list():
    num_lines = sum(1 for line in open(sys.argv[2]))
    list_imgs = {}
    list_imgs['images'] = []
    for i in range(num_lines):
        list_img = {}
        list_img['id'] = i
        if(i < range(num_lines)):
            list_img['name'] = open(sys.argv[2]).readlines()[i].split('\n')
        list_imgs['images'].append(list_img)
    return json.dumps(list_imgs) 


if __name__ == '__main__':
    establish_connection()
    app.run(debug = True)
