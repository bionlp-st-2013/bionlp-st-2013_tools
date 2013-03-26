#!/usr/bin/perl -w
use strict;
use warnings;
use CGI;

my $wdir = './work';
system ("rm -r $wdir/*");
