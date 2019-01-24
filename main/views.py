#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from django.shortcuts import render_to_response
from django.http.response import HttpResponse
from django.db.models import Q
from models import Record
import commands, json, logging, os, re, threading, Queue

logger = logging.getLogger("default")

def mapping(request, method):
    if not method:
        method = "index"
    return eval(method)(request)

def index(request):
    username = request.COOKIES.get("username", "")
    return render_to_response("starter.html", {"username":username})

# 配置分发
def confissue(request):
    return render_to_response("confissue.html")

def syn(ip, q, appname):
    shpath = "/root/gceasy"
    propath = "/root/gceasy/%s" % appname
    os.system('ssh -o StrictHostKeyChecking=no root@%s "[ %s ] && mkdir -p %s"' % (ip, propath, propath))
    rscmd = 'rsync -e "ssh -o StrictHostKeyChecking=no" -a %s/ root@%s:%s/' % (shpath, ip, propath)
    status, rsshell = commands.getstatusoutput(rscmd)
    logger.info(str(rscmd) + " -- code:" + str(status))
    if status:
        code = 500
        msg = "Error: Rsync conf is failed."
    else:
        shcmd = 'ssh -o StrictHostKeyChecking=no root@%s "/bin/sh %s/iniconfig.sh %s"' % (ip, propath, appname)
        status, shres = commands.getstatusoutput(shcmd)
        logger.info(str(shcmd) + " -- code:" + str(status))
        if status:
            code = 500
            msg = "Error: Script execution error."
        else:
            code = 200
            msg = "Successful."
    q.put({"code": code, "ip": ip, "msg": msg})

def issue(request):
    codelist = []
    q = Queue.Queue()
    iplist = request.POST.get("iplist").strip()
    appname = request.POST.get("appname").strip()
    ips = re.split("[ |,|;|\t|\n]", iplist)
    logger.info(ips)
    for ip in ips:
        t = threading.Thread(target=syn, args=[ip, q, appname])
        t.start()
    while True:
        if q.qsize() == len(ips):
            while not q.empty():
                r = q.get()
                codelist.append(r)
            logger.info(codelist)
            return HttpResponse("\n".join(["IP: %s %s" % (item["ip"], item["msg"]) for item in codelist]))

# 日志分析
def gceasy(request):
    return render_to_response("gceasy.html")

def analyze(request):
    code = 500
    msg, result, reporturl = "", "", ""
    ip = request.GET.get("targetip").strip()
    appname = request.GET.get("appname").strip()
    confpath = "/root/gceasy/%s/logpath.conf" % appname
    getpath = "ssh -o StrictHostKeyChecking=no root@%s \"awk '/path/ {print}' %s\"" % (ip, confpath)
    try:
        fpath = commands.getoutput(getpath).split("=")[1]
    except IndexError:
        msg = "Error: Something wrong with ip or appname."
        return HttpResponse(json.dumps({"code": code, "msg": msg}))
    tpath = "/data/joblog"
    os.system('[ %s ] && mkdir -p %s' % (tpath, tpath))
    getlog = 'rsync -e "ssh -o StrictHostKeyChecking=no" -a root@%s:%s %s/' % (ip, fpath, tpath)
    status, gclog = commands.getstatusoutput(getlog)
    logger.info(str(getlog) + " -- code:" + str(status))
    if status:
        msg = "Error: Something wrong with getlog."
    else:
        path = "%s/java-gc.log" % tpath
        arg = "-s -X POST --data-binary"
        apiKey = "6d79606b-28d1-4bf5-a03e-64e28b0422ea"
        contype = '--header "Content-Type:text"'
        getreport = 'curl %s @%s https://api.gceasy.io/analyzeGC?apiKey=%s %s' % (arg, path, apiKey, contype)
        status, result = commands.getstatusoutput(getreport)
        logger.info(getreport)
        logger.info(result)
        data = json.loads(result)
        if "graphURL" not in data.keys():
            msg = "Error: Something wrong with report."
        else:
            reporturl = data["graphURL"]
            Record(ip=ip, url=reporturl).save()
            code = 200
    return HttpResponse(json.dumps({"code":code, "msg":msg, "reporturl":reporturl, "result":result}))

# 历史记录
def hisrecord(request):
    records = Record.objects.all()
    return render_to_response("hisrecord.html", {"records":records})

def checkhis(request):
    checkip = request.GET.get("checkip", "").strip()
    stime = request.GET.get("starttime", "").strip()
    etime = request.GET.get("endtime", "").strip()
    logger.info("checkrecordip:" + str(checkip) + " starttime:" + str(stime) + " endtime:" + str(etime))
    if stime == etime == "":
        records = Record.objects.filter(ip=checkip)
    elif stime == etime:
        records = Record.objects.filter(Q(ip=checkip), Q(time__gt=stime, time__lt="%s 23:59:59" % etime))
    else:
        records = Record.objects.filter(Q(ip=checkip), Q(time__gt="%s 23:59:59" %stime, time__lt=etime))
    return render_to_response("hisrecord.html", {"records":records, "checkip":checkip})