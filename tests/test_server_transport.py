import os
import unittest
from unittest.mock import patch

import server


class ServerTransportTests(unittest.TestCase):
    def test_default_transport_is_stdio(self):
        args = server.parse_args([])
        self.assertEqual(args.transport, "stdio")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8732)
        self.assertEqual(args.path, "/mcp")
        self.assertEqual(args.mode, "runtime")

    def test_streamable_http_args(self):
        args = server.parse_args([
            "--transport", "streamable-http",
            "--host", "127.0.0.1",
            "--port", "9999",
            "--path", "/custom-mcp",
        ])
        self.assertEqual(args.transport, "streamable-http")
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port, 9999)
        self.assertEqual(args.path, "/custom-mcp")

    def test_env_transport(self):
        with patch.dict(os.environ, {
            "ENTROFLOW_MCP_TRANSPORT": "streamable-http",
            "ENTROFLOW_MCP_HOST": "0.0.0.0",
            "ENTROFLOW_MCP_PORT": "8733",
            "ENTROFLOW_MCP_PATH": "/mcp",
        }):
            args = server.parse_args([])
        self.assertEqual(args.transport, "streamable-http")
        self.assertEqual(args.host, "0.0.0.0")
        self.assertEqual(args.port, 8733)
        self.assertEqual(args.path, "/mcp")

    def test_create_mcp_accepts_http_settings(self):
        args = server.parse_args(["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "9999"])
        mcp = server.create_mcp(args)
        self.assertIsNotNone(mcp)

    def test_default_register_tools_exposes_runtime_only(self):
        args = server.parse_args([])
        mcp = server.register_tools(server.create_mcp(args), args.mode)
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        self.assertEqual(tool_names, {"device_search", "device_status", "device_control"})

    def test_all_mode_registers_setup_and_runtime_tools(self):
        args = server.parse_args(["--mode", "all"])
        mcp = server.register_tools(server.create_mcp(args), args.mode)
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        self.assertIn("platform_connect_qr", tool_names)
        self.assertIn("platform_devices", tool_names)
        self.assertIn("device_setup", tool_names)
        self.assertIn("device_control", tool_names)

    def test_setup_mode_registers_setup_only(self):
        args = server.parse_args(["--mode", "setup"])
        mcp = server.register_tools(server.create_mcp(args), args.mode)
        tool_names = {tool.name for tool in mcp._tool_manager.list_tools()}
        self.assertIn("platform_connect_qr", tool_names)
        self.assertIn("device_setup", tool_names)
        self.assertNotIn("device_control", tool_names)


if __name__ == "__main__":
    unittest.main()
