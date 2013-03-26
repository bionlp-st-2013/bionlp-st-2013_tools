#!/usr/bin/perl -w
use strict;
use warnings;
use LWP;
use CGI;
use HTML::Template;

my $logfile  = 'submit.log';
my $errfile  = 'error.log';
my $listfile = 'files.lst';
my $sfile    = 'submission.tar.gz';
my $gdir     = 'gold';
my $wdir     = 'work';
my $cdir     = 'collect';


# to specify the scripts for format checking and evaluation.
my $checker     = "../tools/a2-normalize.pl -u -g $gdir";
my $evaluator   = "../tools/a2-evaluate.pl -g $gdir";


# these two are specific to the GE task
my $decomposer  = "../tools/a2-decompose.pl";
my $devaluator  = "../tools/a2d-evaluate.pl -g $gdir";


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

my $query   = new CGI;
my $email   = $query->param('email');
my $fname   = $query->param('file');
#my $verbose = $query->param('verbose');

## check input fields
if (!$userlist{$email})    {&PrintMessage("Your E-mail address is not registered.")}
if ($fname !~ /\.tar.gz$/) {&PrintMessage("We accept submission of a *.tar.gz file containing all *.a2 files.")}

&logging($email, "access."); 

#if ($verbose eq 'on') {$evaluator .= ' -v'}

## prepare working directory
$wdir .= '/' . $email;

umask 0000;
mkdir($wdir, 0777) || &PrintMessage("Your previous submission is still being processed. Please retry after a moment.");

## prepare files to be tested
my ($buf, $file) = ('', '');
my $fh = $query->upload('file');
while (read($fh, $buf, 1024)) {$file .= $buf}

if (!open (FILE, '>' . $wdir . '/'. $sfile)) {
    system ("rm -r $wdir");
    &logging($email, "failed to open the working file.");
    &PrintMessage("Failed to open the working file. Please try again.")
} # if
print FILE $file;
close (FILE);

my $cmd = "/bin/tar -xzf $wdir/$sfile -C $wdir";
my $errmsg = `$cmd 2>&1`;
if ($errmsg) {
    sleep 2;
    $errmsg = `$cmd 2>&1`;
} # if

if ($errmsg) {
    system ("rm -r $wdir");
    &logging ($email, "failed to unpack:\n$errmsg\n" . `which tar`);
    &PrintMessage("Failed to unpack. Please check your tar.gz file and try again.");
} # if


open (FILE, '<' . $listfile) ;
my @pmid = <FILE>; chomp (@pmid);
close (FILE);

my @missingfile = ();
foreach (@pmid) {
    my $fname = "$_.a2";
    if (! -e "$wdir/$fname") {push @missingfile, $fname}
} # foreach

my $msg = '';

if (@missingfile) {
    &logging ($email, $#missingfile+1 . " missing files.");
    # my $num_miss = $#missingfile+1;
    # $msg = ">>INCOMPLETE SUBMISSION<<<br/>Your submission misses $num_miss file(s).<br/>The evaluation results below are only for the files you have submitted.";
    &PrintMessage("Your submission is missing the following file(s):<ul><li>" . join ("</li><li>", @missingfile) . "</li></ul>");
} # if

system ("/usr/bin/chmod -R 777 $wdir");
system ("/usr/bin/dos2unix $wdir/*.a2");

# check format of the files
$cmd = "$checker $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
if ($errmsg) {
    system ("rm -r $wdir");
    $errmsg =~ s/$wdir\///g;
    &logging ($email, "format error detected.\n");
    &errlog  ($email, "format error detected:\n$errmsg\n");
    &PrintMessage("The following problem(s) were detected in your submission:<br/><pre>$errmsg</pre>");
} # if


# to decompose events (it is specific to the GE task)
$cmd = "$decomposer $wdir/*.a2 2>&1";
$errmsg = `$cmd`;
# skip error checking


# to collect the submissions
# if (!$msg) {
#     my ($sec, $min, $hour, $day, $mon) = (localtime)[0 .. 4]; $mon++;
#     my $ctime = "$mon-$day-$hour-$min-$sec";
#     $cmd = "cp $wdir/$sfile $cdir/$email-$ctime.tar.gz";
#     $errmsg = `$cmd`;
# } # if


## evaluation

# for task 1
my $result1     = `$evaluator  -t1     $wdir/*.a2`;
my $result1sp   = `$evaluator  -t1 -ps $wdir/*.a2`;
my $result1Sp   = `$evaluator  -t1 -pS $wdir/*.a2`;
my $result1spd  = `$devaluator -t1 -ps $wdir/*.a2d`;
my $result1Spd  = `$devaluator -t1 -pS $wdir/*.a2d`;

# for task 2
my $result2d    = `$devaluator -t2     $wdir/*.a2d`;
my $result2spd  = `$devaluator -t2 -ps $wdir/*.a2d`;
my $result2Spd  = `$devaluator -t2 -pS $wdir/*.a2d`;


# for task 3
my $result3    = `$evaluator -t3      $wdir/*.a2`;
my $result3sp  = `$evaluator -t3  -ps $wdir/*.a2`;
my $result3Sp  = `$evaluator -t3  -pS $wdir/*.a2`;

system ("rm -r $wdir");

my $logmsg = "got evaluation results\n##### TASK 1\n[approx span/recursive]\n$result1sp\n##### TASK 2\n[approx span/recursive/decompose]\n$result2spd\n##### TASK 3\n[approx span/recursive]\n$result3sp\n\n";

my @logmsg = split /\n/, $logmsg;
$logmsg = join "\n", grep {!/^\[F[PN]]  /} @logmsg;


&logging ($email, $logmsg . "\n");
#&PrintMessage("evaluation done!");


&PrintResult($msg,
             $result1,  $result1sp,  $result1Sp, $result1spd, $result1Spd,
             $result2d, $result2spd, $result2Spd,
             $result3,  $result3sp,  $result3Sp);



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


sub PrintResult {
    my ($msg,
	$result1,  $result1sp,  $result1Sp, $result1spd, $result1Spd,
	$result2d, $result2spd, $result2Spd,
	$result3,  $result3sp,  $result3Sp) = @_;

    my $template = HTML::Template->new(filename => 'result.tmpl');

    $template->param(MESSAGE => $msg,
		     RESULT1  => $result1,  RESULT1SP   => $result1sp,  RESULT1ZP  => $result1Sp,  RESULT1SPD => $result1spd, RESULT1ZPD => $result1Spd,
		     RESULT2D => $result2d, RESULT2SPD  => $result2spd, RESULT2ZPD => $result2Spd,
		     RESULT3  => $result3,  RESULT3SP   => $result3sp,  RESULT3ZP  => $result3Sp);
    print "Content-Type: text/html\n\n", $template->output;
    exit;
} # PrintResult


sub PrintMessage {
    my ($msg) = shift;
    my $template = HTML::Template->new(filename => 'message.tmpl');

    $template->param(MSG => $msg);
    print "Content-Type: text/html\n\n", $template->output;
    exit;
} # PrintMessage
