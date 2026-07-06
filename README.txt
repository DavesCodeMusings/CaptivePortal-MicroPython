CaptivePortal-MicroPython

A captive portal implementation in MicroPython that provides a minimal DNS
server and HTTP server in addition to the usual MicroPython WiFi access point.
All DNS lookups will return the microcontroller's IP address. Any internet
HTTP request will return a "307 Redirect" to the microcontroller's IP address
and the portal.html page.


Example:

1. A connection is made to the access point from a client machine.
2. The client machine is assigned an IP address along with the DNS server
   address of the microcontroller.
3. The client machine performs captive portal detection by trying to load
   a known web URL.
4. The microcontroller's DNS server returns the address of the microcontroller.
5. The microcontroller's HTTP server returns a 307 Redirect to portal.html
   at the microcontroller's IP.
6. portal.html is served from the microcontroller's flash file system. 
7. The client machine realizes it has not received its expected portal
   detection page.
8. The portal.html page from the microcontroller is displayed instead.

At this point, a regular captive portal would ask for a login or an agreement
to usage terms, and release the client machine to the internet. CaptivePortal-
MicroPython does not do this. It simply keeps the client machine locked to
the microcontroller. Only HTML pages on the flash file system will be served
by the HTTP server.

This can be used to create a sort of WiFi bulletin board as shown by the
project's sample main.py. Create an SSID that entices people to connect and
then deliver a simple informational web page.


Caveats:

The DNS and HTTP hijacking method used by this captive portal has been
superseded by RFC-8910. This specifies a REST API and a DHCP option that
points to the API's URL. MicroPython's access point does not support DHCP
options. However, the older method still works with many client devices.

The HTTP server will serve any file it can find on the flash file system.
This includes requests for boot.py, main.py, and any other files you may
have stored. Do not store passwords or sensitive information.


See also:

   https://support.mozilla.org/en-US/kb/captive-portal
   https://www.ietf.org/rfc/rfc8910.pdf
