"""Offline API-key contracts. Synthetic keys are assembled at runtime."""

from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

import httpx
from google import genai

import api_credentials
import vertex_client as ai


def sample_key(vertex=False):
    return ('AQ.' if vertex else 'AIza') + 'OfflineOnlyNotARealCredential12345678'


class KeySettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target, name, value in [
            (ai, 'ROOT', self.root), (ai, 'SETTINGS_PATH', self.root/'settings.json'),
            (ai, '_normalize_settings_line', lambda line=None: line or 'herogame'),
        ]:
            p = patch.object(target, name, value); p.start(); self.addCleanup(p.stop)
        p = patch.dict(ai.os.environ, {}, clear=True); p.start(); self.addCleanup(p.stop)
        p = patch.dict(api_credentials._session, {}, clear=True); p.start(); self.addCleanup(p.stop)
        ai.get_client.cache_clear()
        self.addCleanup(ai.get_client.cache_clear)

    def test_session_storage_public_status_and_per_line_isolation(self):
        key = sample_key()
        saved = ai.save_settings(ai.VertexSettings(api_key=key))
        self.assertNotIn(key, repr(saved))
        self.assertNotIn(key, json.dumps(ai.status()))
        self.assertNotIn('api_key', ai._saved_data())
        self.assertEqual(ai.load_saved_settings().api_key, key)
        self.assertEqual(ai.load_saved_settings('deskpet').api_key, '')
        api_credentials._session.clear()
        self.assertEqual(ai.load_saved_settings().api_key, '')

    def test_clear_suppresses_environment_key_for_current_session_only(self):
        with patch.dict(ai.os.environ, {'STUDIO_API_KEY': sample_key()}):
            self.assertTrue(ai.load_saved_settings().api_key)
            ai.save_settings(ai.VertexSettings(), clear_api_key=True)
            self.assertFalse(ai.load_saved_settings().api_key)
            self.assertTrue(ai.load_saved_settings('deskpet').api_key)

    def test_invalid_key_preserves_saved_settings(self):
        old = ai.save_settings(ai.VertexSettings(api_key=sample_key(), text_model='custom-text'))
        before = ai.settings_path_for().read_bytes()
        with self.assertRaises(ValueError):
            ai.save_settings(ai.VertexSettings(api_key='invalid key with spaces'))
        self.assertEqual(ai.settings_path_for().read_bytes(), before)
        self.assertEqual(ai.load_saved_settings(), old)

    def test_remember_is_explicit_and_disk_failure_restores_system_secret(self):
        vault = {}
        ring = Mock()
        ring.get_password.side_effect = lambda service, slot: vault.get(slot)
        ring.set_password.side_effect = lambda service, slot, key: vault.__setitem__(slot, key)
        ring.delete_password.side_effect = lambda service, slot: vault.pop(slot)
        with patch.object(api_credentials, '_keyring', return_value=ring):
            ai.save_settings(ai.VertexSettings(api_key=sample_key()), remember_api_key=True)
            api_credentials._session.clear()
            self.assertEqual(ai.load_saved_settings().api_key, sample_key())
            with patch.object(ai, 'write_json', side_effect=OSError('disk full')):
                with self.assertRaisesRegex(RuntimeError, '原设置'):
                    ai.save_settings(ai.VertexSettings(api_key=sample_key(True)), remember_api_key=True)
            self.assertEqual(ai.load_saved_settings().api_key, sample_key())
            ai.save_settings(ai.VertexSettings(), clear_api_key=True)
            self.assertEqual(vault, {})
            self.assertFalse(ai.load_saved_settings().api_key)

    def test_unavailable_credential_store_does_not_fall_back_to_plaintext(self):
        with patch.object(api_credentials, '_keyring', side_effect=RuntimeError('store unavailable')):
            with self.assertRaises(RuntimeError):
                ai.save_settings(ai.VertexSettings(api_key=sample_key()), remember_api_key=True)
        self.assertFalse(ai.settings_path_for().exists())
        self.assertFalse(api_credentials._session)

    def test_task_snapshot_keeps_old_key_when_settings_change(self):
        ai.save_settings(ai.VertexSettings(api_key=sample_key()))
        snapshot = ai.merge_settings(None)
        ai.save_settings(ai.VertexSettings(api_key=sample_key(True)))
        self.assertEqual(ai.merge_settings(snapshot).api_key, sample_key())
        self.assertEqual(ai.merge_settings(None).api_key, sample_key(True))

    def test_explicit_provider_overrides_prefix_and_legacy_adc_fields_are_ignored(self):
        ai.settings_path_for().write_text(json.dumps({'project':'legacy-placeholder', 'location':'old-region', 'text_model':'old-text'}))
        self.assertFalse(ai.load_saved_settings().api_key)
        explicit = ai.VertexSettings(provider='ai_studio', api_key=sample_key(True))
        self.assertEqual(explicit.resolved_provider, 'ai_studio')
        self.assertEqual(ai.VertexSettings(api_key=sample_key(True)).resolved_provider, 'vertex')
        self.assertNotIn('project', ai.status())


class KeyTransportTests(unittest.TestCase):
    def tearDown(self):
        ai.get_client.cache_clear()

    def test_real_sdk_routes_both_keys_without_adc_or_project_and_uses_header(self):
        original = genai.Client
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={'totalTokens':2})
        def factory(**kwargs):
            options = kwargs.pop('http_options').model_copy(update={'client_args':{'transport':httpx.MockTransport(handler), 'trust_env':False}})
            return original(**kwargs, http_options=options)
        with patch.object(ai.genai, 'Client', side_effect=factory), \
             patch('google.auth.default', side_effect=AssertionError('ADC must not be called')), \
             patch.dict(ai.os.environ, {'GOOGLE_CLOUD_PROJECT':'ignored-project', 'GOOGLE_CLOUD_LOCATION':'ignored-region', 'GOOGLE_GENAI_USE_VERTEXAI':'true'}):
            for vertex in (False, True):
                key = sample_key(vertex)
                ai.get_client.cache_clear()
                client = ai.get_client('auto', key)
                client.models.count_tokens(model='test-model', contents='ping')
                request = requests[-1]
                self.assertEqual(request.headers['x-goog-api-key'], key)
                self.assertNotIn(key, str(request.url))
                self.assertNotIn('/projects/', request.url.path)
                self.assertNotIn('authorization', request.headers)
                self.assertEqual(request.url.host, 'aiplatform.googleapis.com' if vertex else 'generativelanguage.googleapis.com')
                client.close()

    def test_json_image_and_probe_use_snapshot_and_never_generate_during_probe(self):
        model = Mock()
        model.count_tokens.return_value = SimpleNamespace(total_tokens=2)
        model.generate_content.return_value = SimpleNamespace(text='{"name":"fox"}')
        cfg = ai.VertexSettings(api_key=sample_key())
        with patch.object(ai, 'get_client', return_value=SimpleNamespace(models=model)) as get:
            self.assertEqual(ai.infer_json('system','user',cfg), '{"name":"fox"}')
            part = SimpleNamespace(text=None, inline_data=SimpleNamespace(data=b'png-fixture'))
            model.generate_content.return_value = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
            self.assertEqual(ai.generate_image('draw',[],settings=cfg)[0], b'png-fixture')
            model.generate_content.reset_mock()
            result = ai.probe(cfg)
            self.assertTrue(result['ok'])
            self.assertEqual(model.count_tokens.call_count,2)
            model.generate_content.assert_not_called()
            self.assertNotIn(sample_key(), json.dumps(result))
            self.assertEqual(get.call_args.args, ('auto',sample_key()))

    def test_error_redaction_and_no_quota_retry(self):
        error = RuntimeError('429 RESOURCE_EXHAUSTED ' + sample_key())
        fn = Mock(side_effect=error)
        with self.assertRaises(RuntimeError) as result:
            ai._call_with_backoff(fn, api_key=sample_key())
        self.assertNotIn(sample_key(), str(result.exception))
        fn.assert_called_once()

    def test_gemini_speech_wraps_pcm_and_cloud_client_never_uses_adc(self):
        import tts_client as tts
        inline = SimpleNamespace(data=b'\0\0'*4, mime_type='audio/L16;codec=pcm;rate=24000')
        response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[SimpleNamespace(inline_data=inline)]))])
        models = Mock(); models.generate_content.return_value = response
        cfg = ai.VertexSettings(api_key=sample_key())
        with patch.object(tts, 'get_client', return_value=SimpleNamespace(models=models)), \
             patch('google.auth.default', side_effect=AssertionError('ADC must not be called')):
            data = tts.synthesize('你好', voice_name='Charon', engine='gemini', settings=cfg)
            with wave.open(BytesIO(data),'rb') as audio:
                self.assertEqual(audio.getframerate(),24000)
                self.assertEqual(audio.getnframes(),4)
            client = tts._client(settings=cfg)
            self.assertEqual(type(client.transport._credentials).__name__, 'Credentials')
            self.assertEqual(client.transport._credentials.token, sample_key())
            client.transport.close()
        with self.assertRaisesRegex(ValueError, 'Express'):
            tts._client(settings=ai.VertexSettings(api_key=sample_key(True)))

    def test_clone_request_uses_key_header_and_never_reads_adc(self):
        import tts_client as tts
        response = Mock()
        response.__enter__ = Mock(return_value=BytesIO(b'{"voiceCloningKey":"offline-voice-handle"}'))
        response.__exit__ = Mock(return_value=False)
        cfg = ai.VertexSettings(api_key=sample_key())
        with patch.object(tts.urllib.request, 'urlopen', return_value=response) as send, \
             patch('google.auth.default', side_effect=AssertionError('ADC must not be called')):
            handle = tts.generate_clone_key(b'a'*8000, b'b'*4000, settings=cfg)
        self.assertEqual(handle, 'offline-voice-handle')
        request = send.call_args.args[0]
        headers = {name.lower():value for name,value in request.header_items()}
        self.assertEqual(headers['x-goog-api-key'],sample_key())
        self.assertNotIn('authorization',headers)

    def test_express_bgm_is_rejected_before_unsupported_api_call(self):
        import bgm_client
        with self.assertRaisesRegex(ValueError, 'Express'):
            bgm_client.generate_stage_bgm(display_name='sample', visual='sample', settings=ai.VertexSettings(api_key=sample_key(True)))



class KeyApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import test_stability
        await test_stability.StudioApiTests.asyncSetUp(self)
        for target, name, value in [(ai,'ROOT',self.root), (ai,'SETTINGS_PATH',self.root/'settings.json')]:
            p=patch.object(target,name,value);p.start();self.addCleanup(p.stop)
        p=patch.dict(ai.os.environ,{},clear=True);p.start();self.addCleanup(p.stop)
        p=patch.dict(api_credentials._session,{},clear=True);p.start();self.addCleanup(p.stop)
        p=patch.object(self.server,'vertex_status',side_effect=ai.status);p.start();self.addCleanup(p.stop)
        self.addCleanup(ai.get_client.cache_clear)

    async def post(self,path,data):
        import test_stability
        return await test_stability.StudioApiTests.post(self,path,data)

    async def test_settings_api_never_returns_secret_and_failed_probe_keeps_old_key(self):
        key=sample_key()
        response=await self.post('/api/settings',{'api_key':key,'provider':'auto'})
        self.assertEqual(response.status_code,200)
        self.assertNotIn(key,response.text)
        for path in ('/api/health','/api/settings'):
            response=await self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertNotIn(key,response.text)
        model=Mock();model.count_tokens.side_effect=RuntimeError('API key not valid '+sample_key(True))
        with patch.object(ai,'get_client',return_value=SimpleNamespace(models=model)):
            response=await self.post('/api/test-auth',{'api_key':sample_key(True),'provider':'auto'})
        self.assertFalse(response.json()['ok'])
        self.assertNotIn(sample_key(True),response.text)
        self.assertEqual(ai.load_saved_settings().api_key,key)
        response=await self.post('/api/settings',{'clear_api_key':True})
        self.assertFalse(response.json()['settings']['api_key_set'])

    async def test_malformed_secret_is_not_echoed_in_validation_error(self):
        key=sample_key()
        response=await self.post('/api/settings',{'api_key':[key]})
        self.assertEqual(response.status_code,422)
        self.assertNotIn(key,response.text)
        self.assertNotIn('input',response.text)

    async def test_successful_probe_saves_redacted_settings_without_generating_content(self):
        model=Mock();model.count_tokens.return_value=SimpleNamespace(total_tokens=1)
        with patch.object(ai,'get_client',return_value=SimpleNamespace(models=model)):
            response=await self.post('/api/test-auth',{'api_key':sample_key(True),'provider':'auto'})
        self.assertTrue(response.json()['ok'])
        self.assertIsNone(response.json()['checks']['tts']['ok'])
        self.assertEqual(response.json()['settings']['resolved_provider'],'vertex')
        self.assertEqual(ai.load_saved_settings().api_key,sample_key(True))
        model.generate_content.assert_not_called()

    async def test_wave_audio_preview_and_commit_use_correct_paths_and_metadata(self):
        import test_stability
        await test_stability.StudioApiTests.open_project(self)
        ai.save_settings(ai.VertexSettings(api_key=sample_key()))
        self.server._write_bible('fox',{'hero_id':'fox','display_name':'离线样例', 'voice':{'tts_voice':'Charon','tts_engine':'gemini','lines':{'intro':{'text':'你好'}}}})
        line_id=self.server.VOICE_LINES[0]['id']
        bible=self.server._read_bible('fox')
        bible['voice']['lines']={line_id:{'text':'你好'}}
        self.server._write_bible('fox',bible)
        output=BytesIO()
        with wave.open(output,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(b'\0\0'*4)
        synth=Mock(return_value=output.getvalue())
        with patch.object(self.server,'_tts',return_value=(Mock(),Mock(),synth)):
            response=await self.post('/api/tts/speak',{'hero_id':'fox','line_id':line_id})
            self.assertEqual(response.status_code,200,response.text)
            self.assertIn('.wav?',response.json()['url'])
            response=await self.post('/api/voice/commit',{'hero_id':'fox'})
            self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(self.server.game_voice_mp3('fox',line_id).with_suffix('.wav').is_file())
        self.assertTrue(self.server._voice_assets('fox')[line_id]['url'])
        self.assertEqual(synth.call_args.kwargs['settings'].api_key,sample_key())


if __name__ == '__main__':
    unittest.main()
