"""Exercise the actual browser lifecycle code with Node; no student fixtures copied."""
import shutil
import subprocess
import unittest
from pathlib import Path


class ChatSessionTests(unittest.TestCase):
    def test_client_lifecycle_and_ime_counterexamples(self):
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required to verify the client lifecycle')
        page = (Path(__file__).resolve().parents[1] / 'src/curriculum_assistant/web/index.html').read_text(encoding='utf-8')
        lifecycle = page.split('/* SESSION_START:')[1].split('*/', 1)[1].split('/* SESSION_END */')[0]
        checks = r'''
const assert=require('node:assert/strict');
const student={student_state_id:'TEST-CHAT-A',course_attempts:[{course_id:'CDA0143'}],applicability_status:'UNVERIFIED'};
const s=new ChatSession();assert.equal(s.applied,null);
s.apply(student);student.course_attempts[0].course_id='changed outside';
assert.equal(s.applied.course_attempts[0].course_id,'CDA0143');
const first=s.beginQuery();assert.equal(s.beginQuery(),null,'duplicate send must be blocked');
const upload=s.selectUpload({name:'TEST.pdf'});
assert.equal(s.queryCurrent(first),true,'file selection must preserve applied-state query');
assert.equal(s.finishQuery(first,{last_course_id:'CDA0143'}),true);
assert.equal(s.context.last_course_id,'CDA0143');
s.resetUpload();assert.equal(s.uploadCurrent(upload),false);
assert.equal(s.applied.student_state_id,'TEST-CHAT-A');assert.equal(s.context.last_course_id,'CDA0143');
const previous=s.beginQuery();s.apply({student_state_id:'TEST-CHAT-B',course_attempts:[]});
assert.equal(s.queryCurrent(previous),false,'late old-student result must be ignored');
assert.equal(s.finishQuery(previous,{last_course_id:'BAD'}),false);assert.deepEqual(s.context,{});
assert.equal(previous.state.student_state_id,'TEST-CHAT-A','historical input must be immutable');
assert.equal(previous.state.course_attempts.length,1);assert.equal(s.applied.course_attempts.length,0,'replace, never merge');
const current=s.beginQuery();assert.equal(s.finishQuery(previous),false);assert.equal(s.queryCurrent(current),true);
current.state.course_attempts.push({course_id:'simulation'});assert.equal(s.applied.course_attempts.length,0);
s.resetAll();assert.equal(s.applied,null);assert.equal(s.pending,null);assert.deepEqual(s.context,{});assert.equal(s.queryCurrent(current),false);
const tokenA=s.selectUpload({name:'A'}),tokenB=s.selectUpload({name:'B'});
assert.equal(s.uploadCurrent(tokenA),false);assert.equal(s.uploadCurrent(tokenB),true);
const reextract=++s.uploadGeneration;
assert.equal(s.uploadCurrent(tokenB),false,'a repeat extraction invalidates previous work on the same file');
assert.equal(s.uploadCurrent(reextract),true);
assert.equal(shouldSendEnter({key:'Enter'},false),true);
for(const event of [{key:'Enter',shiftKey:true},{key:'Enter',isComposing:true},{key:'Enter',keyCode:229},{key:'a'}])assert.equal(shouldSendEnter(event,false),false);
assert.equal(shouldSendEnter({key:'Enter'},true),false);
console.log('PASS: lifecycle, stale requests, snapshots, replacement, simulation isolation, IME');
'''
        run = subprocess.run([node, '-e', lifecycle + checks], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_page_has_no_persistent_student_storage(self):
        page = (Path(__file__).resolve().parents[1] / 'src/curriculum_assistant/web/index.html').read_text(encoding='utf-8')
        for forbidden in ('localStorage', 'sessionStorage', 'indexedDB'):
            self.assertNotIn(forbidden, page)


if __name__ == '__main__':
    unittest.main()
