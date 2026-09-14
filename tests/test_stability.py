import os,sys,tempfile,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from app.config_builder import build_singbox_config
from app.settings import Settings
from app.singbox import SingBoxManager,list_our_singbox_processes,SINGBOX_EXE
from app.connection_check import read_exact,check_https_proxy

class RegressionTests(unittest.TestCase):
 def test_bootstrap_precedes_selected_server_domain(self):
  settings=Settings(vless_url='vless://11111111-2222-3333-4444-555555555555@vpn.example.com:443',enabled={'custom':True},custom_domains=['example.com'])
  cfg=build_singbox_config(settings)
  self.assertEqual(cfg['dns']['rules'][0],{'domain':['vpn.example.com'],'server':'dns-bootstrap'})
  self.assertEqual(cfg['route']['final'],'direct')
  if not SINGBOX_EXE.exists(): self.skipTest('Local sing-box binary not installed')
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'check.json'; path.write_text(json.dumps(cfg))
   result=subprocess.run([str(SINGBOX_EXE),'check','-c',str(path)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
 def test_unknown_or_unrelated_process_never_owned(self):
  with patch('app.singbox.list_singbox_processes',return_value=[(1,''),(2,r'C:\other\bin\sing-box.exe'),(3,str(SINGBOX_EXE))]):
   self.assertEqual(list_our_singbox_processes(),[(3,str(SINGBOX_EXE))])
 def test_stop_never_scans_or_kills_unmanaged(self):
  manager=SingBoxManager.__new__(SingBoxManager); manager.external_instances=MagicMock(side_effect=AssertionError('scan'))
  proc=MagicMock(); proc.poll.return_value=None; manager._proc=proc; manager._output=None
  manager.stop(); proc.terminate.assert_called_once(); proc.wait.assert_called_once(); self.assertIsNone(manager._proc)
 def test_fragmented_socks_response(self):
  sock=MagicMock(); sock.recv.side_effect=[b'\x05',b'\x00']
  self.assertEqual(read_exact(sock,2),b'\x05\x00')
 def test_closed_socks_response(self):
  sock=MagicMock(); sock.recv.return_value=b''
  with self.assertRaises(ConnectionError): read_exact(sock,2)
 def test_proxy_rejects_non_socks(self):
  sock=MagicMock(); sock.__enter__.return_value=sock; sock.recv.return_value=b'XX'
  with patch('app.connection_check.socket.create_connection',return_value=sock):
   with self.assertRaises(ConnectionError): check_https_proxy(1234,'example.com')

if __name__ == '__main__':
 unittest.main()
