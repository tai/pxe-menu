* menu.cgi - Dynamic syslinux menu generation

A weird imagination is most useful to gain full advantage of all the features. -- amd(8) manpage

* Notes
While this document itself is still valid (and the tool is also
actively used (at least by me)), many other things has changed:

- TAR package is not distributed anymore - please do a git clone from github.
- I no longer maintain live demo site.
-- I used to recommend trying BKO (http://boot.kernel.org/) as it was
   somewhat close, bt it also seems gone.
- AFAIK, instead of gPXE, iPXE (http://ipxe.org/) is now recommended.

* What is this?

Menu.cgi is a web CGI script to generate syslinux boot menu over HTTP.
Since its integration with gPXE/Etherboot, SYSLINUX 3.70 and after supports
non-TFTP protocols for network booting. This means you can do many
obscure^H^H^H useful things, such as:

- Browse and boot from files on remote web server through SYSLINUX menu.
- Generate miniroot image on-the-fly, customizing it dynamically as needed.
- Boot directly from image attached on some wiki page :-) 

This script handles first two use-cases.

As an example, I now do "mount --rbind /nfs /tftp/nfs" and let this
script generate appropriate boot entries for whatever kernels installed
under NFSroot environment. This is a real time saver for me, as
I no longer need to update bootmenu every time I setup new kernel
image or nfsroot tree for test environment.

* Major Features

With this script, you can:

- Freely browse folders and boot from any files.
- No more menu editing. Just place files and off you go.
- Generate menu dynamically from custom template.
- Embed scripts in Perl and simplify maintainance (or make more complex one).
- Search across menu entries and show result as a menu.
- Grep through numerous menu entries using Perl expression.
- Generate cpio/tar/gzip archive on-the-fly.
- Edit and boot directly from your custom initramfs in extracted form.
- Rewrite file content on-the-fly with s/match/replace/ expression.
- Stuck with hardcoded NFSroot path in *BSD pxeboot? Just substitute it.

More functionality can by added by extending custom menu template in
configuration file.

* Installation

Installation is easy. Just extract distributed package ("menu.tgz") in
your "tftpboot" folder and make it accessible from the Web. Everything,
including menu.c32 and depending Perl libraries are packaged (You might
want to update or relocate these dependent files).

After extraction is done, try booting with following syslinux entry:

  label remote
    kernel http://location/of/menu.c32
    append http://location/of/menu.cgi

Once booted, you should see syslinux menu entry with a list of folder content.

* Usage

Currently, menu.cgi supports 2 parameters: 'q=' and 'r='.
'q=' is the primary parameter used to specify target for menu generation.

- With "q=folder", folder listing will be returned.
- With "q=file", file content will be returned.
- With "q=query", menu entries are grepped with given query, and matching
  entries will be returned.

For "q=query", you can specify Perl expression.

- With "q=m,debian,", menu entries with the word "debian" will be listed.
- With "q=m,debian,+and+m,sid,", menu entries with the word "debian"
  AND "sid" will be listed.
- With "q=m,debian,+and+not+m,sid,", menu entries with the word "debian"
  BUT NOT "sid" will be listed.

This syntax is somewhat limited, as you need to avoid using "/" and
various non-alphanumeral characters due to security restrictions and
URI escaping rule.

When "q=file" is specified, "r=" can be optionally specified to filter
file content. For example, with "r=s,/nfsroot,/n/fb70a,g", all "/nfsroot"
in that file will be replaced into "/n/fb70a".

This kludgy feature exists to rewrite hardcoded NFSroot path in *BSD
pxeboot image. Although *BSD pxeboot can obtain NFSroot path through
DHCP option, that won't work when I'm chainloading into *BSD pxeboot
from PXELINUX. If anyone can provide me better way to boot NFSroot-ed *BSD,
that is very appreciated.

Lastly, you can pass other parameters, and they can be referenced in
template to customize evaluation behavior. However, please avoid using
single-character parameter as it is reserved for future usage.

* Configuration

Configuration can be done in either "/etc/syslinux/mcgi.config" or
"./.mcgi.config" file. These are loaded as Perl script file, and
customization is done by defining certain variables.

Following is an example of configuration:

  # define location of various files
  $CONFIG->{LIB_URI} = "http://labs.aobac.net/boot/syslinux/lib/";
  $CONFIG->{CGI_URI} = "http://labs.aobac.net/boot/menu.cgi";
  1;
  
  # define template as Perl __DATA__ block
  __DATA__
  label reload
    kernel <%= $LIB_URI %>/menu.c32
    append <%= $CGI_URI %>?<%= $ENV{QUERY_STRING} %>
  
Configuration variables "$CONFIG->{LIB_URI}" and "$CONFIG->{CGI_URI}"
are used to specify location of syslinux module folder and menu.cgi itself.
By default, these are automatically determined, but you should probably
specify "$CONFIG->{LIB_URI}" to use latest syslinux modules (or just
overwrite bundled one).

Custom menu template goes after __DATA__ block. "__DATA__" is a
special Perl token to define data block which can be read like normal
external file. Content of __DATA__ block should contain
Text::ScriptTemplate(3pm) template, expandable to SYSLINUX menu
format (details in next section).

* Template Configuration

Menu template is expanded by evaluating embedded Perl expression.
Two rules of expansion are:

  Rule #1:
  Block surrounded by '<%=' and '%>' will be replaced with its evaluated
  result. This means '<%= 1 + 2 %>' will result to '3' in final output.

  Rule #2:
  Block surrounded by '<%' and '%>' defines non-expanded part of a script.
  This means '<% $FOO = 123 %>' defines variable '$FOO', but no output is
  generated.

So, with template like below, only user with correct keyword will be able
to access hidden boot entry:

  <% if ($CGI->param('keyword') eq 'hogehoge') { %>
  label betatest
    kernel http://example.com/boot/really-beta-kernel
    initrd http://example.com/boot/really-beta-initrd
    append root=/dev/nfs rw ip=dhcp nfsroot=<%= $ENV{HTTP_HOST} %>:/betatest
  <% } %>

Now, the question is: what variables do I have access to in template?
Well, here's the list of available variables:

- $CONFIG
  This is a hash which contains whatever you defined in configuration.
  So if you wrote "$CONFIG->{FOO} = 123;", you can refer to it by
  "$CONFIG->{FOO}".

- $CGI
  This is a CGI::Simple object which holds decoded query parameter.
  So if you called CGI as "http://host/menu.cgi?myparam=123", you can
  refer to "myparam" value by "$CGI->param('myparam')".

- $CGI_URI
  This variable contains URL of called CGI.

- $LIB_URI
  This variable contains URL of SYSLINUX library folder.

- $UPLEVEL
  This variable contains "parent" path of the path specified with
  "q=" CGI parameter.

- $LIST
  This holds a list of menu entries to expand in template.
  Each element is a hash with following structure:

    $entry = {
      name => "entry name probably suitable for LABEL entry",
      type => "typecode or suffix of found entry",
      path => "relative path, valid as menu.cgi?q= parameter",
      uri => "absolute URL of above 'menu.cgi?q=path' location"
      ... # other fields depends on type
    };

  For actual typecode or field content, please refer to included samples.

Other standard variables like "%ENV" are available as well.

* License

This script is free software; you can redistribute it and/or modify
it under the same terms as SYSLINUX. Other bundled copyrighted materials
follow each license.

* References
- Syslinux Project
-- http://www.syslinux.org/wiki/index.php/The_Syslinux_Project
- Etherboot/gPXE Project
-- http://etherboot.org/wiki/start
- gPXE - HTTP booting
-- http://etherboot.org/wiki/httpboot
- Syslinux - syntax
-- http://www.syslinux.org/wiki/index.php/SYSLINUX
- Syslinux - menu.c32
-- http://www.syslinux.org/wiki/index.php/Comboot/menu.c32

* Authors/Contributors
- Taisuke Yamada <tai+syslinux@remove-this-if-not-spam.cc.rakugaki.org>
