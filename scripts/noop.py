"""Minimal asynchronous HTTP endpoint for generator calibration; no database work."""
import asyncio
async def handle(reader,writer):
    try:
        while True:
            await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'),timeout=60)
            writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
            await writer.drain()
    except (asyncio.TimeoutError,ConnectionError,asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()
async def main():
    server=await asyncio.start_server(handle,'127.0.0.1',8099,backlog=4096)
    async with server:
        await server.serve_forever()
if __name__=='__main__': asyncio.run(main())
