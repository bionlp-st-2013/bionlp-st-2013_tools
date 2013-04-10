#!/usr/bin/perl -w
use strict;
use warnings;
use LWP;
use CGI;
use HTML::Template;
use Email::MIME;
use Try::Tiny;

my $logfile  = 'submit.log';
my $errfile  = 'error.log';
my $listfile = 'files.lst';
my $sfile    = 'submission.tar.gz';
my $qfile    = 'questionnaire.txt';
my $gdir     = 'gold';
my $wdir     = 'work';
my $cdir     = 'collect';

# to specify the scripts for format checking and evaluation.
# GE task uses two scripts: checker and decomposer.
my $checker     = "../tools/a2-normalize.pl -u -g $gdir";
my $decomposer  = "../tools/a2-decompose.pl";

## to get the list of registered users
my %userlist;
my $ua = LWP::UserAgent->new;
$ua->credentials('ml.bionlp-st.org:80', 'Restricted Area', 'sharedtask' => '2013acl');
my $res = $ua->get('http://ml.bionlp-st.org/list');
my @email = split(/\n/, $res->content);
if (!@email) {&PrintMessage("Cannot get the list of registered e-mails")}
foreach (@email) {
    chomp;
    $userlist{$_} = 1;
}
###

my $query       = new CGI;
my $name        = $query->param('name');
my $affiliation = $query->param('affiliation');
my $email       = $query->param('email');
my $fname       = $query->param('file');

# $name = "Jin-Dong Kim";
# $affiliation = "DBCLS";
# $email = 'jdkim@dbcls.rois.ac.jp';
# $fname = "a.tar.gz";

## check input fields
if (!$name)                {&PrintMessage("Please enter your name.")}
if (!$affiliation)         {&PrintMessage("Please enter your affiliation.")}
if (!$userlist{$email})    {&PrintMessage("Your E-mail address is not registered.")}
if ($fname !~ /\.tar.gz$/) {&PrintMessage("We only accept submission of a *.tar.gz file containing the all *.a2 files.")}

&logging($email, "access with task: GE."); 

## prepare working directory
$wdir .= '/' . $email;

umask 0000;
mkdir($wdir, 0777) || &PrintMessage("Your previous submission is still being processed. Please wait and retry.");

## prepare files to be tested
my ($buf, $file) = ('', '');
my $fh = $query->upload('file');
while (read($fh, $buf, 1024)) {$file .= $buf}

if (!open (FILE, '>' . $wdir . '/'. $sfile)) {
    system ("rm -r $wdir");
    &logging($email, "failed to open the working file.\n");
    &PrintMessage("Failed to open a working file. Please try again.");
} # if
print FILE $file;
close (FILE);


## unpack files
my $cmd = "tar -xzf $wdir/$sfile -C $wdir";
my $errmsg = `$cmd 2>&1`;
if ($errmsg) {
    sleep 2;
    $errmsg = `$cmd 2>&1`;
} # if

if ($errmsg) {
    system ("rm -r $wdir");
    &logging ($email, "failed to unpack:\n$errmsg\n");
    &PrintMessage("Failed to unpack. Please check your tar.gz file and try again.");
} # if


## check missing or extra files
open (FILE, '<' . $listfile) ;
my @pmid = <FILE>; chomp (@pmid);
close (FILE);
my %pmid = map { $_ => 1 } @pmid;

my @extrafile = ();

opendir(WDIR, $wdir);
while (my $fname = readdir(WDIR)) {
    next if ($fname eq '.' || $fname eq '..' || $fname eq 'submission.tar.gz');
    if ($pmid{$fname}) {delete $pmid{$fname}}
    else {
        push @extrafile, $fname;
        system("rm $wdir/$fname");
    }
}
closedir(WDIR);

my @missingfile = sort keys %pmid;

if (@missingfile || @extrafile) {
    system ("rm -r $wdir");
    &logging ($email, $#missingfile+1 . " missing files.");
    &logging ($email, $#extrafile+1 . " extra files.");

    $errmsg = '';
    if (@missingfile) {$errmsg .= "<p>missing:<ul><li>" . join ("</li><li>", @missingfile) . "</li></ul></p>"}
    if (@extrafile)   {$errmsg .= "<p>extra:<ul><li>"   . join ("</li><li>", @extrafile) . "</li></ul></p>"}

    &PrintMessage("Your submission has missing and/or extra file(s)." . $errmsg);
} # if
###


system ("chmod -R 777 $wdir");
system ("dos2unix $wdir/*.a2");

# check format of the files
$cmd = "$checker $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
if ($errmsg) {
    system ("rm -r $wdir");
    $errmsg =~ s/$wdir\///g;
    &logging ($email, "format error detected.\n");
    &errlog  ($email, "format error detected.\n$errmsg\n");
    &PrintMessage("Following formatting problem(s) detected in your submission:<br/><pre>$errmsg</pre>");
} # if


# to decompose events (it is specific to the GE task)
$cmd = "$decomposer $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
if ($errmsg) {
    system ("rm -r $wdir");
    $errmsg =~ s/$wdir\///g;
    &logging ($email, "logical error detected.\n");
    &errlog  ($email, "logical error detected:\n$errmsg\n");
    &PrintMessage("The following problem(s) were detected in your submission:<br/><pre>$errmsg</pre>");
} # if


# submission collection
my ($sec, $min, $hour, $day, $mon) = (localtime)[0 .. 4]; $mon++;
my $ctime = sprintf("%02d-%02d-%02d-%02d-%02d", $mon, $day, $hour, $min, $sec);
$cmd = "cp $wdir/$sfile $cdir/$email-$ctime.tar.gz";
$errmsg = `$cmd`;
system ("rm -r $wdir");

&SendNotification($name, $email, $ctime);

&logging ($email, "submission accepted.\n");
&PrintMessage("Your submission is accepted without problem.<br/>A notification mail is sent to you.<br/>Thank you for your participation!");


sub logging {
    my ($email, $event) = @_;
    open (LOGFILE, ">> $logfile") ;
    flock(LOGFILE, 2);
    seek(LOGFILE, 0, 2);
    my $datetime = localtime;
    print LOGFILE "[$datetime / $email] $event\n" ;
    flock(LOGFILE, 8);
    close (LOGFILE);
} # logging


sub errlog {
    my ($email, $event) = @_;
    open (LOGFILE, ">> $errfile") ;
    flock(LOGFILE, 2);
    seek(LOGFILE, 0, 2);
    my $datetime = localtime;
    print LOGFILE "[$datetime / $email] $event\n" ;
    flock(LOGFILE, 8);
    close (LOGFILE);
} # errlog


sub PrintMessage {
    my ($msg) = shift;
    my $template = HTML::Template->new(filename => 'message.tmpl');

    $template->param(MSG => $msg);
    print "Content-Type: text/html\n\n", $template->output;
    exit;
} # PrintMessage


sub SendNotification {
    my ($name, $email, $time) = @_;


    my $body = <<"BODY";
Dear $name,

Your submission to BioNLP-ST 2013 GE task is accepted.

Please note that you can make a submission again.
Among your multiple submissions, only the last one
will be regarded as your final submission.

Evalutation results will be announced on 16th April
as scheduled:

http://2013.bionlp-st.org/schedule

Thank you very much for your participation.

Best Regards,

BioNLP-ST 2013 GE task organizers
BODY


    my $message = Email::MIME->create(
      header_str => [
        From    => 'bionlp-st-ge@googlegroups.com',
        To      => $email,
        CC      => 'bionlp-st-ge@googlegroups.com',
        Subject => "[bionlp-st-ge]Submission accepted ($time)",
      ],
      attributes => {
        encoding => 'quoted-printable',
        charset  => 'ISO-8859-1',
      },
      body_str => $body,
    );

    # send the message
    use Email::Sender::Simple qw(sendmail);

    try {
        sendmail($message);
    } catch {
        &PrintMessage("<h3>Notification sending failed</h3><pre>$_</pre>");
    }
}