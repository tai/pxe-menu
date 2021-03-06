#!/usr/bin/perl -Ilib/perl
# -*- coding: utf-8-unix; mode: perl -*-
#
# menu.cgi - syslinux menu generator over HTTP.
#
# Usage:
# http://host/path/to/m.cgi?q=<query>;r=<expr>;...
#
# Query Parameters;
#   q=<query>   : Which folder/file/menu/menuitem to show.
#   r=<perlexpr>: Filter file with given substitution.
#
# Usage Example:
# - http://host/boot/m.cgi?q=.
# - http://host/boot/m.cgi?q=nfsroot/sid64a
# - http://host/boot/m.cgi?q=pxelinux.cfg/debian
# - http://host/boot/m.cgi?q=pxelinux.cfg/dynamic.tmpl
# - http://host/boot/m.cgi?q=m,debian,+and+m,sid,
# - http://host/boot/m.cgi?q=freebsd/pxeboot;r=s,/pxeroot,/n/fb70a,
#
# Author: Taisuke Yamada <tai+syslinux@nospam.cc.rakugaki.org>
#

use DirHandle;
use FileHandle;
use File::Basename;
use File::Find;
use IO::String;
use YAML;
use Safe;
use Cwd qw(realpath);
use CGI::Simple;
use Text::ScriptTemplate;
use strict;
use warnings;

######################################################################
# Default configuration
######################################################################
our $CONFIG = {
  LIB_URI => undef, # where syslinux *.c32 and other files reside
  CGI_URI => undef, # location of this CGI
};

######################################################################
# Internal functions
######################################################################

=item $uri = self_uri();
Returns URI of this CGI.
=cut
sub self_uri {
    my $host = $ENV{HTTP_HOST}   || "localhost";
    my $path = $ENV{SCRIPT_NAME} || "/";

    return "http://${host}${path}";
}

=item $bool = is_menu($path);
Returns true if given file seems to be a syslinux menu file.
=cut
sub is_menu {
    my $path = shift;

    return if -B $path;
    return if $path =~ /\.cgi/;

    my $file = new FileHandle($path) || return;
    while (defined($_ = $file->getline)) {
	return 1 if /^label /io;
    }
}

=item loadmenu($cgi, [@list]);
Expands syslinux menu template.
=cut
sub loadmenu {
    my($cgi, $list, $file) = @_;
    my $arg = {
        CONFIG  => $CONFIG,
        CGI     => $cgi,
        CGI_URI => $CONFIG->{CGI_URI} || self_uri(),
        UPLEVEL => dirname($cgi->param('q') || ""),
        LIST    => $list,
    };
    $arg->{LIB_URI} = $CONFIG->{LIB_URI} || dirname($arg->{CGI_URI});

    return Text::ScriptTemplate->new->load($file)->setq(%$arg)->fill;
}

=item showmenu($cgi, [@list]);
Expands syslinux menu template.
=cut
sub showmenu {
    print "Content-Type: text/plain\n\n";
    print loadmenu(@_, \*DATA);
}

=item genfail($cgi, $message);
Generates and returns error screen in a form of syslinux menu to a browser.
=cut
sub genfail {
    my($cgi, $err) = @_;

    showmenu($cgi, [{ type => ":message", text => $err }]);
    exit(0);
}

=item genfile($cgi, $path);
Filters and returns specified file content to a browser.
=cut
sub genfile {
    my($cgi, $path) = @_;

    my $expr = $cgi->param('r');
    my $safe = Safe->new;

    # minimal permission to use "eval" for substitution
    $safe->permit_only(qw{
        null const pushmark uc lc quotemeta match list not and or lineseq
        padany
        leaveeval

        subst
    });

    $_ = join("", FileHandle->new($path)->getlines);
    $safe->reval($expr) if $expr;
    genfail($cgi, $@) if $@;

    print "Content-Type: application/octet-stream\n\n";
    print;
}

=item genmenu($cgi, $path);
Expands and returns specified syslinux menu file to a browser.
=cut
sub genmenu {
    my($cgi, $path) = @_;

    print "Content-Type: text/plain\n\n";
    print loadmenu($cgi, [], $path);
}

=item genlist($cgi, $path, $%hint);
Generates and returns folder index in a form of syslinux menu to a browser.
=cut
sub genlist {
    my($cgi, $path, %hint) = @_;

    my $mcgi = $CONFIG->{CGI_URI} || self_uri();
    my @file = DirHandle->new($path)->read;
    my @list;

    foreach my $name (@file) {
	next if $name =~ /^\./;
        my $item = {
	    hint => { %hint }, # create copy
            name => $name,
            path => "$path/$name",
            base => $path,
            base_uri => "$mcgi?q=$path",
        };

	if (-d $item->{path}) {
            $item->{type} = ':dir';
            $item->{uri}  = "$mcgi?q=$item->{path}";
	}
	elsif ($name =~ /^pxe/) {
            $item->{type} = ':pxe';
            $item->{uri}  = "$mcgi?q=$item->{path}";
        }
        elsif ($name =~ /^xen/) {
            $item->{type} = ':xen';
            $item->{uri}  = "$mcgi?q=$item->{path}";
        }
	elsif ($name =~ /^(linux|vmlinux|vmlinuz|bzimage)(-\S+)?$/) {
            $item->{type}   = ':linux';
            $item->{uri}    = "$mcgi?q=$item->{path}";

	    my @initrd = grep { -f "$path/$_" && /^initrd.*$2\b/    } @file;
            if (@initrd) {
                $item->{initrd} = "$mcgi?q=$path/$initrd[0]";
            }

	    my @iramfs = grep { -f "$path/$_" && /^initramfs.*$2\b/ } @file;
            if (@iramfs) {
                $item->{type}   = ':linux-dracut';
                $item->{initrd} = "$mcgi?q=$path/$iramfs[0]";
            }
	}
	elsif (is_menu($item->{path})) {
            $item->{type} = ':menu';
            $item->{uri}  = "$mcgi?q=$item->{path}";
	}
	elsif ($name =~ /\.(\w+)$/) {
            $item->{type} = $1;
            $item->{uri}  = "$mcgi?q=$item->{path}";
	}
        push(@list, $item) if defined($item->{type});
    }
    @list = sort { $a->{name} cmp $b->{name} } @list;

    showmenu($cgi, \@list);
}

=item genpack($cgi, $path, $type);
Generates and returns packed archive of given folder to a browser.
=cut
sub genpack {
    my($cgi, $base, $type) = @_;
    my $name = basename($base);

    print "Content-Disposition: attachment; filename=$name.$type\n";
    print "Content-Type: application/octet-stream\n\n";

    if ($type eq "cgz") {
        chdir($base);
        system("find . | cpio --quiet -o -H newc | gzip");
    }
    elsif ($type eq "tgz") {
        chdir($base);
        system("tar zcf - .");
    }
    elsif ($type eq "tar") {
        chdir($base);
        system("tar cf - .");
    }
}

=item genscan($cgi, $expr);
Generates dynamic menu from matching menu entries.
=cut
sub genscan {
    my($cgi, $expr) = @_;
    my @list;
    my $safe = Safe->new;

    # minimal permission to use "eval" for query matching
    $safe->permit_only(qw{
        null const pushmark uc lc quotemeta match list not and or lineseq
        padany
        leaveeval
    });

    # scan syslinux menu files
    find(sub {
        my $path = $_;

        $File::Find::prune = 1, return if -d "$_/dev" && -d "$_/etc";
        return unless is_menu($path);

        # expand menu as it could be a template
        my $menu = loadmenu($cgi, [], $path);
        my $file = IO::String->new($menu);
        my @line;

        # lookup each "LABEL" entry
        while (defined($_ = pop(@line) || $file->getline)) {
            next unless /^label /io;

            my $buff = $_;
            while (defined($_ = $file->getline)) {
                next if /^\s*\#/;
                push(@line, $_), last if /^label /io;
                $buff .= $_;
            }

            # pick matching entry
            $_ = $buff;
            push(@list, { type => ":asis", text=>$_ }) if $safe->reval($expr);
            warn $@ if $@;
        }
        $file->close;
    }, '.');

    @list = sort { $a->{text} cmp $b->{text} } @list;

    showmenu($cgi, \@list);
}

######################################################################
# main
######################################################################
my $cgi = CGI::Simple->new;

eval {
    my $path = $cgi->param('q') || ".";
    my $name = basename($path);

    # reject suspicous-looking query
    die "Invalid query: $path"
        if $path =~ m|^/| or $path =~ /\.\./ or $path =~ /[[:cntrl:]]/;

    foreach (qw(/etc/syslinux/mcgi.config .mcgi.config $path/.mcgi.config)) {
        do $_ if -f $_; warn $@ if $@;
    }

    if (-d $path) {
	# hack for nfsroot+aufs
	if (-d "$path/rw" && -l "$path/ro" && -d "$path/ro/boot") {
	    my $here = realpath(".");
	    my $real = realpath("$path/ro") . "/boot";
            $real =~ s|^$here/?||;
	    genlist($cgi, $real, aufs => $path);
	}
	# hack for nfsroot
	elsif (-d "$path/boot" && -d "$path/sbin") {
	    my $real = "$path/boot";
	    genlist($cgi, $real);
	}
	else {
	    genlist($cgi, $path);
	}
    }
    elsif (is_menu($path)) {
        genmenu($cgi, $path);
    }
    elsif (-s $path) {
        genfile($cgi, $path);
    }
    elsif ($path =~ m/^(\S*\w)\.(cgz|tgz|tar)$/ && -d $1) {
        genpack($cgi, $1, $2);
    }
    else {
        genscan($cgi, $path); # handle as query term, not path
    }
};
genfail($cgi, "$@ - $!") if $@;

exit(0);

######################################################################
# Default syslinux menu template
######################################################################
__DATA__
######################################################################
# Standard Preamble
######################################################################
serial 0 115200
prompt 1

######################################################################
# Menu Configuration
######################################################################
menu title DEMO: Dynamic menu over HTTP (<%= $CGI->param('q') %>)
menu margin 1

label self
  menu label .    - Reload
  kernel <%= $LIB_URI %>/menu.c32
  append <%= $CGI_URI %>?<%= $ENV{QUERY_STRING} %>

label prev
  menu label ..   - Go uplevel
  kernel <%= $LIB_URI %>/menu.c32
  append <%= $CGI_URI %>?q=<%= $UPLEVEL %>

label main
  menu label main - Jump to main menu
  kernel <%= $LIB_URI %>/menu.c32

menu separator
label > This is a sample dynamic syslinux menu over HTTP.
label > With menu.cgi, you can:
label >  - Browse folders and boot from files without writing a menu.
label >  - Generate menu dynamically from custom template.
label >  - Search across menu entries and show result as a menu.
menu separator

######################################################################
# Menu Items
######################################################################

<% foreach my $item (grep { $_->{type} eq ':message' } @$LIST) { %>
say <%= $item->{text} %>
<% } %>

<% foreach my $item (grep { $_->{type} eq ':asis' } @$LIST) { %>
<%= $item->{text} %>
<% } %>

<% foreach my $item (grep { $_->{type} eq ':menu' } @$LIST) { %>
label <%= $item->{name} %>
  kernel <%= $LIB_URI %>/menu.c32
  append <%= $item->{uri} %>
<% } %>

<% foreach my $item (grep { $_->{type} eq ':dir' } @$LIST) { %>
label <%= $item->{name} %>
  menu label <%= $item->{name} %>/
  kernel <%= $LIB_URI %>/menu.c32
  append <%= $item->{uri} %>
<% } %>

<% foreach my $item (grep { $_->{type} eq ':pxe' } @$LIST) { %>
label <%= $item->{name} %>
  pxe <%= $item->{uri} %>;r=s,/pxeroot,/n/,
<% } %>

<% foreach my $item (grep { $_->{type} eq ':linux' } @$LIST) { %>
label <%= $item->{name} %>
  kernel <%= $item->{uri} %>
  initrd <%= $item->{initrd} %>
  append panic=30 console=tty0 console=ttyS0,115200 root=/dev/nfs rw ip=dhcp nfsroot=<%= $ENV{HTTP_HOST} %>:/n/
<% } %>

<% foreach my $item (grep { $_->{type} eq ':linux-dracut' } @$LIST) { %>
label <%= $item->{name} %>
  kernel <%= $item->{uri} %>
  initrd <%= $item->{initrd} %>
<% if ($item->{uri} =~ m|\b(n/[^/]+)|) { %>
  append console=tty0 console=ttyS0,115200 ip=dhcp root=nfs:<%= $ENV{HTTP_HOST} %>:/<%= $1 %>:rw,tcp,soft,intr,vers=3
<% } else { %>
  append console=tty0 console=ttyS0,115200 ro root=/dev/ram
<% } %>
<% } %>

<% foreach my $item (grep { $_->{type} eq 'img' } @$LIST) { %>
label <%= $item->{name} %>*
  kernel <%= $LIB_URI %>/memdisk
  append initrd=<%= $item->{uri} %>
<% } %>
