import importlib

from django.shortcuts import render
from django.http import HttpResponse,HttpResponseRedirect
from django.views.decorators.cache import never_cache

from .models import *
try:
    from django.urls import reverse
except:
    from django.core.urlresolvers import reverse
from django.template.context_processors import csrf
from django.template.context import RequestContext
from django.conf import settings
from . import TrustedDevice
from django.contrib.auth.decorators import login_required
from user_agents import parse

@never_cache
@login_required
def index(request):
    keys=[]
    context={"keys":User_Keys.objects.filter(username=request.user.username),"UNALLOWED_AUTHEN_METHODS":settings.MFA_UNALLOWED_METHODS
             ,"HIDE_DISABLE":getattr(settings,"MFA_HIDE_DISABLE",[]),'RENAME_METHODS':getattr(settings,'MFA_RENAME_METHODS',{})}
    for k in context["keys"]:
        k.name = getattr(settings,'MFA_RENAME_METHODS',{}).get(k.key_type,k.key_type)
        if k.key_type =="Trusted Device":
            setattr(k,"device",parse(k.properties.get("user_agent","-----")))
        elif k.key_type == "FIDO2":
            setattr(k,"device",k.properties.get("type","----"))
        elif k.key_type == "RECOVERY":
            context["recovery"] = k
            continue
        keys.append(k)
    context["keys"]=keys
    return render(request,"mfa/MFA.html",context)

@never_cache
def verify(request,username):
    request.session["base_username"] = username
    #request.session["base_password"] = password
    keys=User_Keys.objects.filter(username=username,enabled=1)
    methods=list(set([k.key_type for k in keys]))

    if "Trusted Device" in methods and not request.session.get("checked_trusted_device",False):
        if TrustedDevice.verify(request):
            return login(request)
        methods.remove("Trusted Device")
    request.session["mfa_methods"] = methods

    if len(methods)==1:
        return HttpResponseRedirect(reverse(methods[0].lower()+"_auth"))
    if getattr(settings,"MFA_ALWAYS_GO_TO_LAST_METHOD",False):
        keys = keys.exclude(last_used__isnull=True).order_by("last_used")
        if keys.count()>0:
            return HttpResponseRedirect(reverse(keys[0].key_type.lower() + "_auth"))
    return show_methods(request)

@never_cache
def show_methods(request):
    return render(request,"mfa/select_mfa_method.html", {'RENAME_METHODS':getattr(settings,'MFA_RENAME_METHODS',{})})

@never_cache
def reset_cookie(request):
    response=HttpResponseRedirect(settings.LOGIN_URL)
    response.delete_cookie("base_username")
    return response

@never_cache
def login(request):
    from django.contrib import auth
    from django.conf import settings
    callable_func = __get_callable_function__(settings.MFA_LOGIN_CALLBACK)
    return callable_func(request,username=request.session["base_username"])

@never_cache
@login_required
def delKey(request):
    key=User_Keys.objects.get(id=request.GET["id"])
    if key.username == request.user.username:
        key.delete()
        return HttpResponse("Deleted Successfully")
    else:
        return HttpResponse("Error: You own this token so you can't delete it")

def __get_callable_function__(func_path):
    import importlib
    if not '.' in func_path:
        raise Exception("class Name should include modulename.classname")

    parsed_str = func_path.split(".")
    module_name , func_name = ".".join(parsed_str[:-1]) , parsed_str[-1]
    imported_module = importlib.import_module(module_name)
    callable_func = getattr(imported_module,func_name)
    if not callable_func:
        raise Exception("Module does not have requested function")
    return callable_func

@never_cache
@login_required
def toggleKey(request):
    id=request.GET["id"]
    q=User_Keys.objects.filter(username=request.user.username, id=id)
    if q.count()==1:
        key=q[0]
        if not key.key_type in settings.MFA_HIDE_DISABLE:
            key.enabled=not key.enabled
            key.save()
            return HttpResponse("OK")
        else:
            return HttpResponse("You can't change this method.")
    else:
        return HttpResponse("Error")

@never_cache
def goto(request,method):
    return HttpResponseRedirect(reverse(method.lower()+"_auth"))
