"""Every completed cold-reload path gets guidance; temporary features stay on."""
import unittest
from desktopapp import reloadguide


class ReloadGuideTests(unittest.TestCase):
    def test_all_completed_cold_reload_paths(self):
        cases = [('setup_all','WAIT_RELOAD'), ('direct_fl23_enable','AWAITING_RELOAD'),
            ('direct_fl23_disable','AWAITING_RELOAD'), ('direct_look_import','AWAITING_RELOAD'),
            ('direct_slot_default','AWAITING_RELOAD'), ('direct_factory_reset','AWAITING_RELOAD'),
            ('direct_resume_factory','AWAITING_RELOAD'), ('restore','RESTORED_AWAITING_RELOAD'),
            ('restore_auto','RESTORED_AWAITING_RELOAD'),
            ('sound_on','written'), ('sound_off','restored'), ('sound_install','installed_cold_test_pending'),
            ('sound_restore_sound','restored_cold_test_pending')]
        for action, phase in cases:
            with self.subTest(action=action, phase=phase):
                self.assertTrue(reloadguide.required(action, dict(phase=phase)))

    def test_no_cold_restart_before_audition_or_for_adoption_offline_and_failures(self):
        cases = [('sound_audition','temporary_pcm_registered_cold_reload_required_after_test'),
            ('sound_confirm_recovery','owner_confirmed_cold_recovered'), ('sound_import','converted_offline'),
            ('sound_verify','owner_confirmed_working'), ('vertical_enable','running'),
            ('direct_verify','LOADED'), ('direct_fl23_enable','LOADED'),
            ('direct_fl23_enable','PREFLIGHT_VERIFIED'), ('direct_fl23_enable','NEEDS_REVIEW'),
            ('sound_install','needs_review')]
        for action, phase in cases:
            with self.subTest(action=action):self.assertFalse(reloadguide.required(action, dict(phase=phase)))
        self.assertFalse(reloadguide.required('sound_on', dict(phase='written', adopted_existing_enabled=True)))

    def test_audition_popup_keeps_power_until_listening_not_cold_reload(self):
        result=dict(phase='temporary_pcm_registered_cold_reload_required_after_test')
        self.assertFalse(reloadguide.required('sound_audition',result))
        notice=reloadguide.sound_notice('sound_audition',result)
        for phrase in ('保持相机开机','电子快门','取下电池','临时音效消失','恢复试听前的声音','保存到所选快门'):
            self.assertIn(phrase,notice['text'])
        self.assertNotIn('记录',notice['text']);self.assertNotIn('确认试听正确',notice['text'])

    def test_install_prerequisites_have_distinct_guidance_not_failure_or_fake_completion(self):
        for phase in ('sound_conversion_required',):
            notice=reloadguide.sound_notice('sound_install',dict(phase=phase))
            self.assertIn('保存尚未开始',notice['title'])
            self.assertIn('等待操作',notice['status'])
        for phase in ('needs_review','installed_cold_test_pending'):
            self.assertIsNone(reloadguide.sound_notice('sound_install',dict(phase=phase)))


def test_generic_instructions_need_no_manual_confirmation():
    message=reloadguide.text()
    assert '至少等待 1 分钟'in message
    assert '继续安装'not in message
    assert '已断电恢复原声，记录恢复完成'not in message
