import json
import os
from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.test.utils import override_settings

from api import test_data
from api.models import ACL, AuthEvent
from api.tests import JClient
from authmethods.models import Code
from captcha.models import Captcha

# Create your tests here.

class TestProcessCaptcha(TestCase):
    fixtures = ['initial.json']
    def setUp(self):
        ae = AuthEvent(auth_method="email",
                auth_method_config=test_data.authmethod_config_email_default,
                extra_fields=test_data.ae_email_fields_captcha['extra_fields'],
                status='started',
                census="open")
        ae.save()
        self.ae = ae
        self.aeid = ae.pk

        u_admin = User(username=test_data.admin['username'])
        u_admin.set_password(test_data.admin['password'])
        u_admin.save()
        u_admin.userdata.event = ae
        u_admin.userdata.save()

        acl = ACL(user=u_admin.userdata, object_type='AuthEvent', perm='edit',
            object_id=self.aeid)
        acl.save()

        acl = ACL(user=u_admin.userdata, object_type='AuthEvent', perm='create',
                object_id=0)
        acl.save()

    def tearDown(self):
        # Removed generated captchas
        captcha_dir = settings.STATIC_ROOT + '/captcha/'
        captchas = [f for f in os.listdir(captcha_dir) if f.endswith('.png') ]
        for c in captchas:
            os.remove(captcha_dir + c)


    def test_create_new_captcha(self):
        c = JClient()
        self.assertEqual(0, Captcha.objects.count())
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(1, Captcha.objects.count())

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_pregenerate_captchas(self):
        self.assertEqual(0, Captcha.objects.count())

        c = JClient()
        c.authenticate(0, test_data.admin)
        response = c.post('/api/auth-event/', test_data.ae_email_fields_captcha)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(settings.PREGENERATION_CAPTCHA, Captcha.objects.filter(used=False).count())

    def test_create_authevent_email_with_captcha(self):
        c = JClient()

        # add census without problem with captcha
        c.authenticate(0, test_data.admin)
        response = c.census(self.aeid, test_data.census_email_default)
        self.assertEqual(response.status_code, 200)
        response = c.get('/api/auth-event/%d/census/' % self.aeid, {})
        self.assertEqual(response.status_code, 200)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(r['userids']), 4)

        # add register: without captcha
        response = c.register(self.aeid, test_data.register_email_fields)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

        # create captcha
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        captcha = Captcha.objects.all()[0]
        data = test_data.register_email_fields

        # add register: bad code
        data.update({'captcha_code': '', 'captcha': captcha.challenge})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

        # add register # TODO fix
        data.update({'captcha_code': captcha.code, 'captcha': captcha.challenge})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 200)

        # add register: repeat captcha invalid
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

        # create captcha
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        captcha = Captcha.objects.all()[0]
        data = test_data.register_email_fields

        # add register: bad challenge
        data.update({'captcha_code': captcha.code, 'captcha': ''})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

    def test_create_authevent_sms_with_captcha(self):
        self.ae.auth_method = 'sms'
        self.ae.auth_method_config = test_data.authmethod_config_sms_default
        self.ae.save()
        c = JClient()


        # add census without problem with captcha
        c.authenticate(0, test_data.admin)
        response = c.census(self.aeid, test_data.census_sms_default)
        self.assertEqual(response.status_code, 200)
        response = c.get('/api/auth-event/%d/census/' % self.aeid, {})
        self.assertEqual(response.status_code, 200)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(len(r['userids']), 4)

        # add register: without captcha
        response = c.register(self.aeid, test_data.register_email_fields)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertTrue(r['msg'].count('Invalid captcha'))

        # create captcha
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        captcha = Captcha.objects.all()[0]
        data = test_data.register_sms_default
        data.update({'tlf': '999999999'})

        # add register: bad code
        data.update({'captcha_code': '', 'captcha': captcha.challenge})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

        # add register # TODO fix
        data.update({'captcha_code': captcha.code, 'captcha': captcha.challenge})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 200)

        # add register: repeat captcha invalid
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

        # create captcha
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        captcha = Captcha.objects.all()[0]
        data = test_data.register_sms_fields
        data.update({'tlf': '888888888'})

        # add register: bad challenge
        data.update({'captcha_code': captcha.code, 'captcha': ''})
        response = c.register(self.aeid, data)
        self.assertEqual(response.status_code, 400)
        r = json.loads(response.content.decode('utf-8'))
        self.assertEqual(r['msg'], 'Invalid captcha')

    def test_get_new_captcha_generate_other_captcha(self):
        self.assertEqual(Captcha.objects.count(), 0)
        self.assertEqual(Captcha.objects.filter(used=True).count(), 0)

        c = JClient()
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        r = json.loads(response.content.decode('utf-8'))
        self.assertTrue(r['image_url'] and r['captcha_code'])
        response = c.get('/api/captcha/new/', {})
        self.assertEqual(response.status_code, 200)
        r = json.loads(response.content.decode('utf-8'))
        self.assertTrue(r['image_url'] and r['captcha_code'])

        self.assertEqual(Captcha.objects.count(), 2)
        self.assertEqual(Captcha.objects.filter(used=True).count(), 2)
